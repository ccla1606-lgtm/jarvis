"""PostgreSQL implementation of the canonical task repository."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from jarvis.domain.entities import (
    Approval,
    Artifact,
    ModelResolution,
    Plan,
    PlanStatus,
    PlanStep,
    Run,
    RunStatus,
    TraceLink,
)
from jarvis.domain.errors import ConcurrencyConflictError, EntityNotFoundError
from jarvis.domain.ids import (
    PlanId,
    RunId,
    TaskId,
    TransitionId,
)
from jarvis.domain.task import Task, TaskStatus, TaskTransition
from jarvis.infrastructure.migrations import validate_schema_name

Row = dict[str, Any]


class PostgresTaskRepository:
    """Transactional PostgreSQL adapter with CAS and durable idempotency."""

    def __init__(self, database_url: str, *, schema: str = "public") -> None:
        self._database_url = database_url
        self._schema = validate_schema_name(schema)

    @contextmanager
    def _connection(self) -> Iterator[Connection[Row]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            connection.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema))
            )
            yield connection

    def create_task(self, task: Task, *, idempotency_key: str) -> Task:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key must not be empty")
        with self._connection() as connection:
            claimed = connection.execute(
                """
                INSERT INTO idempotency_records (operation, idempotency_key, entity_id)
                VALUES ('create_task', %s, %s)
                ON CONFLICT (operation, idempotency_key) DO NOTHING
                RETURNING entity_id
                """,
                (key, task.id),
            ).fetchone()
            if claimed is None:
                existing = connection.execute(
                    """
                    SELECT entity_id
                    FROM idempotency_records
                    WHERE operation = 'create_task' AND idempotency_key = %s
                    """,
                    (key,),
                ).fetchone()
                if existing is None:
                    raise RuntimeError("idempotency claim disappeared")
                return self._get_task(connection, TaskId(existing["entity_id"]))

            connection.execute(
                """
                INSERT INTO tasks (id, objective, status, version, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    task.id,
                    task.objective,
                    task.status.value,
                    task.version,
                    task.created_at,
                    task.updated_at,
                ),
            )
            return task

    def get_task(self, task_id: TaskId) -> Task:
        with self._connection() as connection:
            return self._get_task(connection, task_id)

    def list_tasks(self, *, limit: int = 100) -> tuple[Task, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("task list limit must be between 1 and 100")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, objective, status, version, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def _get_task(self, connection: Connection[Row], task_id: TaskId) -> Task:
        row = connection.execute(
            """
            SELECT id, objective, status, version, created_at, updated_at
            FROM tasks
            WHERE id = %s
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise EntityNotFoundError("Task", str(task_id))
        return _task_from_row(row)

    def save_transition(
        self,
        task: Task,
        transition: TaskTransition,
        *,
        expected_version: int,
    ) -> Task:
        if task.version != expected_version + 1:
            raise ValueError("saved task must increment expected_version exactly once")
        if (
            transition.task_id != task.id
            or transition.to_status is not task.status
            or transition.task_version != task.version
        ):
            raise ValueError("transition does not match the task update")

        with self._connection() as connection:
            updated = connection.execute(
                """
                UPDATE tasks
                SET status = %s, version = %s, updated_at = %s
                WHERE id = %s AND version = %s AND status = %s
                RETURNING version
                """,
                (
                    task.status.value,
                    task.version,
                    task.updated_at,
                    task.id,
                    expected_version,
                    transition.from_status.value,
                ),
            ).fetchone()
            if updated is None:
                current = connection.execute(
                    "SELECT version FROM tasks WHERE id = %s",
                    (task.id,),
                ).fetchone()
                if current is None:
                    raise EntityNotFoundError("Task", str(task.id))
                raise ConcurrencyConflictError(
                    "Task",
                    str(task.id),
                    expected_version,
                    current["version"],
                )

            connection.execute(
                """
                INSERT INTO task_transitions (
                    id,
                    task_id,
                    run_id,
                    from_status,
                    to_status,
                    task_version,
                    actor,
                    reason,
                    occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    transition.id,
                    transition.task_id,
                    transition.run_id,
                    transition.from_status.value,
                    transition.to_status.value,
                    transition.task_version,
                    transition.actor,
                    transition.reason,
                    transition.occurred_at,
                ),
            )
            return task

    def list_transitions(self, task_id: TaskId) -> tuple[TaskTransition, ...]:
        with self._connection() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM tasks WHERE id = %s",
                    (task_id,),
                ).fetchone()
                is None
            ):
                raise EntityNotFoundError("Task", str(task_id))
            rows = connection.execute(
                """
                SELECT
                    id,
                    task_id,
                    run_id,
                    from_status,
                    to_status,
                    task_version,
                    actor,
                    reason,
                    occurred_at
                FROM task_transitions
                WHERE task_id = %s
                ORDER BY task_version
                """,
                (task_id,),
            ).fetchall()
        return tuple(_transition_from_row(row) for row in rows)

    def create_plan(self, plan: Plan) -> Plan:
        steps = [
            {
                "position": step.position,
                "description": step.description,
                "depends_on": list(step.depends_on),
                "tools": list(step.tools),
                "repositories": list(step.repositories),
            }
            for step in plan.steps
        ]
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO plans (id, task_id, version, status, steps, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    plan.id,
                    plan.task_id,
                    plan.version,
                    plan.status.value,
                    Jsonb(steps),
                    plan.created_at,
                ),
            )
        return plan

    def get_plan(self, plan_id: PlanId) -> Plan:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, task_id, version, status, steps, created_at
                FROM plans
                WHERE id = %s
                """,
                (plan_id,),
            ).fetchone()
        if row is None:
            raise EntityNotFoundError("Plan", str(plan_id))
        return _plan_from_row(row)

    def get_plan_for_task(self, task_id: TaskId, *, version: int) -> Plan | None:
        if version < 1:
            raise ValueError("plan version must be positive")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, task_id, version, status, steps, created_at
                FROM plans
                WHERE task_id = %s AND version = %s
                """,
                (task_id, version),
            ).fetchone()
        return _plan_from_row(row) if row is not None else None

    def get_latest_plan_for_task(self, task_id: TaskId) -> Plan | None:
        with self._connection() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM tasks WHERE id = %s",
                    (task_id,),
                ).fetchone()
                is None
            ):
                raise EntityNotFoundError("Task", str(task_id))
            row = connection.execute(
                """
                SELECT id, task_id, version, status, steps, created_at
                FROM plans
                WHERE task_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return _plan_from_row(row) if row is not None else None

    def record_approval(self, approval: Approval) -> Approval:
        with self._connection() as connection:
            plan_row = connection.execute(
                """
                SELECT id, task_id, version, status, steps, created_at
                FROM plans
                WHERE id = %s
                FOR UPDATE
                """,
                (approval.plan_id,),
            ).fetchone()
            if plan_row is None:
                raise EntityNotFoundError("Plan", str(approval.plan_id))
            plan = _plan_from_row(plan_row)
            decided_plan = plan.apply_approval(approval)
            connection.execute(
                """
                INSERT INTO approvals (
                    id,
                    task_id,
                    plan_id,
                    plan_version,
                    decision,
                    actor,
                    reason,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    approval.id,
                    approval.task_id,
                    approval.plan_id,
                    approval.plan_version,
                    approval.decision.value,
                    approval.actor,
                    approval.reason,
                    approval.created_at,
                ),
            )
            connection.execute(
                "UPDATE plans SET status = %s WHERE id = %s",
                (decided_plan.status.value, decided_plan.id),
            )
        return approval

    def create_run(self, run: Run) -> Run:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id,
                    task_id,
                    attempt,
                    status,
                    plan_id,
                    plan_version,
                    previous_run_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run.id,
                    run.task_id,
                    run.attempt,
                    run.status.value,
                    run.plan_id,
                    run.plan_version,
                    run.previous_run_id,
                    run.created_at,
                    run.updated_at,
                ),
            )
        return run

    def get_run(self, run_id: RunId) -> Run:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    task_id,
                    attempt,
                    status,
                    plan_id,
                    plan_version,
                    previous_run_id,
                    created_at,
                    updated_at
                FROM runs
                WHERE id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise EntityNotFoundError("Run", str(run_id))
        return _run_from_row(row)

    def list_runs(self, task_id: TaskId) -> tuple[Run, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    task_id,
                    attempt,
                    status,
                    plan_id,
                    plan_version,
                    previous_run_id,
                    created_at,
                    updated_at
                FROM runs
                WHERE task_id = %s
                ORDER BY attempt
                """,
                (task_id,),
            ).fetchall()
            if (
                not rows
                and connection.execute(
                    "SELECT 1 FROM tasks WHERE id = %s",
                    (task_id,),
                ).fetchone()
                is None
            ):
                raise EntityNotFoundError("Task", str(task_id))
        return tuple(_run_from_row(row) for row in rows)

    def add_artifact(self, artifact: Artifact) -> Artifact:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (id, task_id, run_id, kind, uri, sha256, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    artifact.id,
                    artifact.task_id,
                    artifact.run_id,
                    artifact.kind,
                    artifact.uri,
                    artifact.sha256,
                    artifact.created_at,
                ),
            )
        return artifact

    def add_model_resolution(self, resolution: ModelResolution) -> ModelResolution:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO model_resolutions (
                    id,
                    task_id,
                    run_id,
                    profile,
                    provider,
                    model,
                    account,
                    reason,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    resolution.id,
                    resolution.task_id,
                    resolution.run_id,
                    resolution.profile,
                    resolution.provider,
                    resolution.model,
                    resolution.account,
                    resolution.reason,
                    resolution.created_at,
                ),
            )
        return resolution

    def add_trace_link(self, trace_link: TraceLink) -> TraceLink:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO trace_links (
                    id,
                    task_id,
                    run_id,
                    backend,
                    trace_id,
                    url,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace_link.id,
                    trace_link.task_id,
                    trace_link.run_id,
                    trace_link.backend,
                    trace_link.trace_id,
                    trace_link.url,
                    trace_link.created_at,
                ),
            )
        return trace_link


def _task_from_row(row: Row) -> Task:
    return Task(
        id=TaskId(cast(UUID, row["id"])),
        objective=cast(str, row["objective"]),
        status=TaskStatus(cast(str, row["status"])),
        version=cast(int, row["version"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _transition_from_row(row: Row) -> TaskTransition:
    run_id = row["run_id"]
    return TaskTransition(
        id=TransitionId(cast(UUID, row["id"])),
        task_id=TaskId(cast(UUID, row["task_id"])),
        run_id=RunId(run_id) if run_id is not None else None,
        from_status=TaskStatus(cast(str, row["from_status"])),
        to_status=TaskStatus(cast(str, row["to_status"])),
        task_version=cast(int, row["task_version"]),
        actor=cast(str, row["actor"]),
        reason=cast(str, row["reason"]),
        occurred_at=row["occurred_at"],
    )


def _plan_from_row(row: Row) -> Plan:
    raw_steps = cast(list[dict[str, object]], row["steps"])
    return Plan(
        id=PlanId(cast(UUID, row["id"])),
        task_id=TaskId(cast(UUID, row["task_id"])),
        version=cast(int, row["version"]),
        status=PlanStatus(cast(str, row["status"])),
        steps=tuple(
            PlanStep(
                position=cast(int, step["position"]),
                description=cast(str, step["description"]),
                depends_on=tuple(cast(list[int], step.get("depends_on", []))),
                tools=tuple(cast(list[str], step.get("tools", []))),
                repositories=tuple(cast(list[str], step.get("repositories", []))),
            )
            for step in raw_steps
        ),
        created_at=row["created_at"],
    )


def _run_from_row(row: Row) -> Run:
    plan_id = row["plan_id"]
    previous_run_id = row["previous_run_id"]
    return Run(
        id=RunId(cast(UUID, row["id"])),
        task_id=TaskId(cast(UUID, row["task_id"])),
        attempt=cast(int, row["attempt"]),
        status=RunStatus(cast(str, row["status"])),
        plan_id=PlanId(plan_id) if plan_id is not None else None,
        plan_version=cast(int | None, row["plan_version"]),
        previous_run_id=RunId(previous_run_id) if previous_run_id is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
