"""Canonical task aggregate and state machine."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from jarvis.domain.errors import InvalidTransitionError
from jarvis.domain.ids import RunId, TaskId, TransitionId, new_task_id, new_transition_id
from jarvis.domain.time import require_utc, utc_now


class TaskStatus(StrEnum):
    RECEIVED = "RECEIVED"
    TRIAGING = "TRIAGING"
    ANSWERING = "ANSWERING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    NEEDS_REVISION = "NEEDS_REVISION"


_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.RECEIVED: frozenset({TaskStatus.TRIAGING, TaskStatus.CANCELLED, TaskStatus.FAILED}),
    TaskStatus.TRIAGING: frozenset(
        {
            TaskStatus.ANSWERING,
            TaskStatus.PLANNING,
            TaskStatus.QUEUED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.ANSWERING: frozenset(
        {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED, TaskStatus.FAILED}
    ),
    TaskStatus.PLANNING: frozenset(
        {TaskStatus.AWAITING_APPROVAL, TaskStatus.CANCELLED, TaskStatus.FAILED}
    ),
    TaskStatus.AWAITING_APPROVAL: frozenset(
        {
            TaskStatus.QUEUED,
            TaskStatus.REJECTED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED}),
    TaskStatus.RUNNING: frozenset({TaskStatus.VERIFYING, TaskStatus.CANCELLED, TaskStatus.FAILED}),
    TaskStatus.VERIFYING: frozenset(
        {
            TaskStatus.SUCCEEDED,
            TaskStatus.NEEDS_REVISION,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.NEEDS_REVISION: frozenset(
        {TaskStatus.PLANNING, TaskStatus.QUEUED, TaskStatus.CANCELLED}
    ),
    TaskStatus.REJECTED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.QUEUED}),
    TaskStatus.FAILED: frozenset({TaskStatus.QUEUED}),
    TaskStatus.SUCCEEDED: frozenset(),
}

ALLOWED_TASK_TRANSITIONS: Final[Mapping[TaskStatus, frozenset[TaskStatus]]] = MappingProxyType(
    _TRANSITIONS
)


@dataclass(frozen=True, slots=True)
class TaskTransition:
    """Immutable evidence for one accepted state edge."""

    id: TransitionId
    task_id: TaskId
    run_id: RunId | None
    from_status: TaskStatus
    to_status: TaskStatus
    task_version: int
    actor: str
    reason: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.occurred_at)
        if self.task_version < 1:
            raise ValueError("transition task_version must be positive")
        if not self.actor.strip():
            raise ValueError("transition actor must not be empty")
        if not self.reason.strip():
            raise ValueError("transition reason must not be empty")


@dataclass(frozen=True, slots=True)
class Task:
    """Canonical task aggregate with optimistic version."""

    id: TaskId
    objective: str
    status: TaskStatus
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        require_utc(self.updated_at)
        if not self.objective.strip():
            raise ValueError("task objective must not be empty")
        if self.version < 0:
            raise ValueError("task version must not be negative")
        if self.updated_at < self.created_at:
            raise ValueError("task updated_at cannot precede created_at")

    @classmethod
    def create(
        cls,
        objective: str,
        *,
        task_id: TaskId | None = None,
        now: datetime | None = None,
    ) -> "Task":
        timestamp = now or utc_now()
        return cls(
            id=task_id or new_task_id(),
            objective=objective,
            status=TaskStatus.RECEIVED,
            version=0,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def transition(
        self,
        target: TaskStatus,
        *,
        actor: str,
        reason: str,
        run_id: RunId | None = None,
        now: datetime | None = None,
    ) -> tuple["Task", TaskTransition]:
        """Return a new aggregate and append-only transition evidence."""

        if target not in ALLOWED_TASK_TRANSITIONS[self.status]:
            raise InvalidTransitionError(self.status.value, target.value)

        timestamp = now or utc_now()
        updated = replace(
            self,
            status=target,
            version=self.version + 1,
            updated_at=timestamp,
        )
        transition = TaskTransition(
            id=new_transition_id(),
            task_id=self.id,
            run_id=run_id,
            from_status=self.status,
            to_status=target,
            task_version=updated.version,
            actor=actor,
            reason=reason,
            occurred_at=timestamp,
        )
        return updated, transition
