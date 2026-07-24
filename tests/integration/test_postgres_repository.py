from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from jarvis.domain.entities import (
    Approval,
    ApprovalDecision,
    Artifact,
    ModelResolution,
    Plan,
    PlanStatus,
    PlanStep,
    Run,
    RunStatus,
    TraceLink,
)
from jarvis.domain.errors import ApprovalMismatchError, ConcurrencyConflictError
from jarvis.domain.ids import (
    new_artifact_id,
    new_model_resolution_id,
    new_plan_id,
    new_run_id,
    new_task_id,
    new_trace_link_id,
)
from jarvis.domain.task import Task, TaskStatus
from jarvis.domain.time import utc_now
from jarvis.infrastructure.migrations import (
    DEFAULT_MIGRATION_DIRECTORY,
    MigrationChecksumMismatchError,
    apply_migrations,
)
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def test_migrations_create_empty_schema_and_are_idempotent(
    database_url: str,
    postgres_schema: str,
) -> None:
    first = apply_migrations(database_url, schema=postgres_schema)
    second = apply_migrations(database_url, schema=postgres_schema)

    assert first.applied == ("0001_domain.sql", "0002_command_idempotency.sql")
    assert first.current_version == "0002_command_idempotency.sql"
    assert second.applied == ()
    assert second.current_version == first.current_version


def test_migration_checksum_drift_is_rejected(
    database_url: str,
    postgres_schema: str,
    tmp_path: Path,
) -> None:
    migration_directory = tmp_path / "migrations"
    migration_directory.mkdir()
    source = DEFAULT_MIGRATION_DIRECTORY / "0001_domain.sql"
    copied = migration_directory / source.name
    copied.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    apply_migrations(
        database_url,
        schema=postgres_schema,
        migration_directory=migration_directory,
    )
    copied.write_text(
        f"{copied.read_text(encoding='utf-8')}\n-- forbidden edit\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationChecksumMismatchError):
        apply_migrations(
            database_url,
            schema=postgres_schema,
            migration_directory=migration_directory,
        )


def test_concurrent_duplicate_command_returns_original_result(
    postgres_repository: PostgresTaskRepository,
) -> None:
    barrier = Barrier(2)

    def submit(objective: str) -> Task:
        candidate = Task.create(objective)
        barrier.wait()
        return postgres_repository.create_task(
            candidate,
            idempotency_key="same-command",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(submit, ("first", "second")))

    assert results[0].id == results[1].id
    assert results[0].objective == results[1].objective


def test_two_concurrent_updates_have_one_winner_and_one_classified_conflict(
    postgres_repository: PostgresTaskRepository,
) -> None:
    task = postgres_repository.create_task(
        Task.create("Concurrent update"),
        idempotency_key="concurrent-update",
    )
    barrier = Barrier(2)

    def update(target: TaskStatus) -> str:
        current = postgres_repository.get_task(task.id)
        updated, transition = current.transition(
            target,
            actor=target.value,
            reason="concurrency acceptance",
        )
        barrier.wait()
        try:
            postgres_repository.save_transition(
                updated,
                transition,
                expected_version=current.version,
            )
        except ConcurrencyConflictError:
            return "conflict"
        return "winner"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(update, (TaskStatus.TRIAGING, TaskStatus.CANCELLED)))

    assert sorted(outcomes) == ["conflict", "winner"]
    assert postgres_repository.get_task(task.id).version == 1
    assert len(postgres_repository.list_transitions(task.id)) == 1


def test_plan_approval_is_version_bound_and_persisted(
    postgres_repository: PostgresTaskRepository,
) -> None:
    task = postgres_repository.create_task(
        Task.create("Plan"),
        idempotency_key="plan",
    )
    plan = postgres_repository.create_plan(
        Plan.propose(
            task_id=task.id,
            version=2,
            steps=(
                PlanStep(1, "Implement", repositories=("owner/repo",)),
                PlanStep(
                    2,
                    "Verify",
                    depends_on=(1,),
                    tools=("test",),
                    repositories=("owner/repo",),
                ),
            ),
            now=NOW,
        )
    )
    assert postgres_repository.get_plan_for_task(task.id, version=2) == plan
    stale = Approval.record(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=1,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="stale approval",
        now=NOW,
    )

    with pytest.raises(ApprovalMismatchError):
        postgres_repository.record_approval(stale)
    assert postgres_repository.get_plan(plan.id).status is PlanStatus.PROPOSED

    current = Approval.record(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=2,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="current approval",
        now=NOW,
    )
    postgres_repository.record_approval(current)

    assert postgres_repository.get_plan(plan.id).status is PlanStatus.APPROVED


def test_retry_and_state_survive_repository_restart(
    database_url: str,
    postgres_schema: str,
) -> None:
    apply_migrations(database_url, schema=postgres_schema)
    first_process = PostgresTaskRepository(database_url, schema=postgres_schema)
    task = first_process.create_task(
        Task.create("Durable task", now=NOW),
        idempotency_key="durable",
    )
    transitioned, event = task.transition(
        TaskStatus.TRIAGING,
        actor="process-one",
        reason="persist before restart",
        now=NOW,
    )
    first_process.save_transition(
        transitioned,
        event,
        expected_version=task.version,
    )
    failed = first_process.create_run(
        Run.queue(task_id=task.id, now=NOW).with_status(RunStatus.FAILED, now=NOW)
    )
    retry = first_process.create_run(failed.retry(now=NOW))

    second_process = PostgresTaskRepository(database_url, schema=postgres_schema)

    assert second_process.get_task(task.id) == transitioned
    assert second_process.list_transitions(task.id) == (event,)
    assert second_process.get_run(failed.id) == failed
    assert second_process.list_runs(task.id) == (failed, retry)


def test_missing_entities_are_classified(
    postgres_repository: PostgresTaskRepository,
) -> None:
    from jarvis.domain.errors import EntityNotFoundError

    with pytest.raises(EntityNotFoundError):
        postgres_repository.get_task(new_task_id())
    with pytest.raises(EntityNotFoundError):
        postgres_repository.get_plan(new_plan_id())
    with pytest.raises(EntityNotFoundError):
        postgres_repository.get_run(new_run_id())
    with pytest.raises(EntityNotFoundError):
        postgres_repository.list_transitions(new_task_id())
    with pytest.raises(EntityNotFoundError):
        postgres_repository.list_runs(new_task_id())


def test_immutable_evidence_entities_are_recorded(
    postgres_repository: PostgresTaskRepository,
) -> None:
    task = postgres_repository.create_task(
        Task.create("Evidence"),
        idempotency_key="evidence",
    )
    run = postgres_repository.create_run(Run.queue(task_id=task.id, now=NOW))
    created_at = utc_now()
    artifact = Artifact(
        id=new_artifact_id(),
        task_id=task.id,
        run_id=run.id,
        kind="patch",
        uri="file:///artifacts/change.patch",
        sha256="a" * 64,
        created_at=created_at,
    )
    resolution = ModelResolution(
        id=new_model_resolution_id(),
        task_id=task.id,
        run_id=run.id,
        profile="coder",
        provider="fake",
        model="deterministic",
        account=None,
        reason="integration evidence",
        created_at=created_at,
    )
    trace = TraceLink(
        id=new_trace_link_id(),
        task_id=task.id,
        run_id=run.id,
        backend="otel",
        trace_id="0" * 32,
        url=None,
        created_at=created_at,
    )

    assert postgres_repository.add_artifact(artifact) == artifact
    assert postgres_repository.add_model_resolution(resolution) == resolution
    assert postgres_repository.add_trace_link(trace) == trace
