"""Framework-independent Jarvis domain model."""

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
    DomainError,
    EntityNotFoundError,
    InvalidRetryError,
    InvalidTransitionError,
)
from jarvis.domain.task import ALLOWED_TASK_TRANSITIONS, Task, TaskStatus, TaskTransition

__all__ = [
    "ALLOWED_TASK_TRANSITIONS",
    "Approval",
    "ApprovalDecision",
    "ApprovalMismatchError",
    "Artifact",
    "ConcurrencyConflictError",
    "DomainError",
    "EntityNotFoundError",
    "InvalidRetryError",
    "InvalidTransitionError",
    "ModelResolution",
    "Plan",
    "PlanStatus",
    "PlanStep",
    "Run",
    "RunStatus",
    "Task",
    "TaskStatus",
    "TaskTransition",
    "TraceLink",
]
