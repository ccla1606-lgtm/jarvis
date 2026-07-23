from dataclasses import replace
from datetime import UTC, datetime

import pytest

from jarvis.application.task_service import TaskService
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
from jarvis.domain.errors import (
    ApprovalMismatchError,
    ConcurrencyConflictError,
    EntityNotFoundError,
)
from jarvis.domain.ids import (
    new_artifact_id,
    new_model_resolution_id,
    new_plan_id,
    new_run_id,
    new_task_id,
    new_trace_link_id,
)
from jarvis.domain.task import Task, TaskStatus
from jarvis.infrastructure.memory_repository import InMemoryTaskRepository

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def test_duplicate_idempotency_key_returns_original_task() -> None:
    repository = InMemoryTaskRepository()
    original = Task.create("Original", now=NOW)
    duplicate = Task.create("Different candidate", now=NOW)

    first = repository.create_task(original, idempotency_key="request-1")
    second = repository.create_task(duplicate, idempotency_key="request-1")

    assert first == original
    assert second == original


def test_stale_update_is_classified_and_does_not_append_history() -> None:
    repository = InMemoryTaskRepository()
    task = repository.create_task(Task.create("Task", now=NOW), idempotency_key="task")
    first, first_event = task.transition(
        TaskStatus.TRIAGING,
        actor="one",
        reason="first writer",
        now=NOW,
    )
    stale, stale_event = task.transition(
        TaskStatus.CANCELLED,
        actor="two",
        reason="stale writer",
        now=NOW,
    )

    repository.save_transition(first, first_event, expected_version=task.version)
    with pytest.raises(ConcurrencyConflictError):
        repository.save_transition(stale, stale_event, expected_version=task.version)

    assert repository.get_task(task.id) == first
    assert repository.list_transitions(task.id) == (first_event,)


def test_repository_rejects_approval_for_other_plan_version() -> None:
    repository = InMemoryTaskRepository()
    task = repository.create_task(Task.create("Task", now=NOW), idempotency_key="task")
    plan = repository.create_plan(
        Plan.propose(
            task_id=task.id,
            version=2,
            steps=(PlanStep(1, "Implement"),),
            now=NOW,
        )
    )
    approval = Approval.record(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=1,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="wrong version",
        now=NOW,
    )

    with pytest.raises(ApprovalMismatchError):
        repository.record_approval(approval)

    assert repository.get_plan(plan.id).status is PlanStatus.PROPOSED


def test_service_retry_preserves_previous_attempt() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)
    task = service.submit("Task", idempotency_key="task")
    failed = repository.create_run(
        Run.queue(task_id=task.id, now=NOW).with_status(RunStatus.FAILED, now=NOW)
    )

    retry = service.retry_run(failed.id)

    assert repository.list_runs(task.id) == (failed, retry)
    assert retry.previous_run_id == failed.id


def test_repository_classifies_missing_entities_and_duplicate_versions() -> None:
    repository = InMemoryTaskRepository()
    missing_task_id = new_task_id()

    with pytest.raises(ValueError, match="idempotency"):
        repository.create_task(Task.create("Task", now=NOW), idempotency_key=" ")
    with pytest.raises(EntityNotFoundError):
        repository.get_task(missing_task_id)
    with pytest.raises(EntityNotFoundError):
        repository.list_transitions(missing_task_id)
    with pytest.raises(EntityNotFoundError):
        repository.list_runs(missing_task_id)
    with pytest.raises(EntityNotFoundError):
        repository.get_plan(new_plan_id())
    with pytest.raises(EntityNotFoundError):
        repository.get_run(new_run_id())

    task = repository.create_task(Task.create("Task", now=NOW), idempotency_key="task")
    plan = repository.create_plan(
        Plan.propose(
            task_id=task.id,
            version=1,
            steps=(PlanStep(1, "Step"),),
            now=NOW,
        )
    )
    with pytest.raises(ValueError, match="already exists"):
        repository.create_plan(
            Plan.propose(
                task_id=task.id,
                version=1,
                steps=(PlanStep(1, "Other"),),
                now=NOW,
            )
        )
    run = repository.create_run(Run.queue(task_id=task.id, now=NOW))
    with pytest.raises(ValueError, match="already exists"):
        repository.create_run(Run.queue(task_id=task.id, attempt=run.attempt, now=NOW))

    missing_approval = Approval.record(
        task_id=task.id,
        plan_id=new_plan_id(),
        plan_version=1,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="missing",
        now=NOW,
    )
    with pytest.raises(EntityNotFoundError):
        repository.record_approval(missing_approval)
    assert repository.get_plan(plan.id) == plan


def test_repository_validates_transition_shape_and_missing_parent() -> None:
    repository = InMemoryTaskRepository()
    missing = Task.create("Missing", now=NOW)
    updated, event = missing.transition(
        TaskStatus.TRIAGING,
        actor="agent",
        reason="missing",
        now=NOW,
    )
    with pytest.raises(EntityNotFoundError):
        repository.save_transition(updated, event, expected_version=0)

    task = repository.create_task(Task.create("Task", now=NOW), idempotency_key="task")
    updated, event = task.transition(
        TaskStatus.TRIAGING,
        actor="agent",
        reason="valid",
        now=NOW,
    )
    with pytest.raises(ValueError, match="increment"):
        repository.save_transition(
            replace(updated, version=2),
            event,
            expected_version=task.version,
        )


def test_repository_records_ancillary_evidence_and_checks_parent() -> None:
    repository = InMemoryTaskRepository()
    task = repository.create_task(Task.create("Task", now=NOW), idempotency_key="task")
    artifact = Artifact(
        new_artifact_id(),
        task.id,
        None,
        "patch",
        "file:///patch",
        "a" * 64,
        NOW,
    )
    resolution = ModelResolution(
        new_model_resolution_id(),
        task.id,
        None,
        "coder",
        "fake",
        "model",
        None,
        "selected",
        NOW,
    )
    trace = TraceLink(
        new_trace_link_id(),
        task.id,
        None,
        "otel",
        "trace",
        None,
        NOW,
    )

    assert repository.add_artifact(artifact) == artifact
    assert repository.add_model_resolution(resolution) == resolution
    assert repository.add_trace_link(trace) == trace

    missing_id = new_task_id()
    with pytest.raises(EntityNotFoundError):
        repository.add_artifact(
            Artifact(
                new_artifact_id(),
                missing_id,
                None,
                "patch",
                "file:///patch",
                "b" * 64,
                NOW,
            )
        )
