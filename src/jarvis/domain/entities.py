"""Immutable domain entities owned by Jarvis."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from jarvis.domain.errors import ApprovalMismatchError, InvalidRetryError
from jarvis.domain.ids import (
    ApprovalId,
    ArtifactId,
    ModelResolutionId,
    PlanId,
    RunId,
    TaskId,
    TraceLinkId,
    new_approval_id,
    new_plan_id,
    new_run_id,
)
from jarvis.domain.time import require_utc, utc_now


class PlanStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_REVISION = "NEEDS_REVISION"


@dataclass(frozen=True, slots=True)
class PlanStep:
    position: int
    description: str

    def __post_init__(self) -> None:
        if self.position < 1:
            raise ValueError("plan step position must be positive")
        if not self.description.strip():
            raise ValueError("plan step description must not be empty")


@dataclass(frozen=True, slots=True)
class Approval:
    id: ApprovalId
    task_id: TaskId
    plan_id: PlanId
    plan_version: int
    decision: ApprovalDecision
    actor: str
    reason: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        if self.plan_version < 1:
            raise ValueError("approval plan_version must be positive")
        if not self.actor.strip():
            raise ValueError("approval actor must not be empty")
        if not self.reason.strip():
            raise ValueError("approval reason must not be empty")

    @classmethod
    def record(
        cls,
        *,
        task_id: TaskId,
        plan_id: PlanId,
        plan_version: int,
        decision: ApprovalDecision,
        actor: str,
        reason: str,
        now: datetime | None = None,
    ) -> "Approval":
        return cls(
            id=new_approval_id(),
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
            decision=decision,
            actor=actor,
            reason=reason,
            created_at=now or utc_now(),
        )


@dataclass(frozen=True, slots=True)
class Plan:
    id: PlanId
    task_id: TaskId
    version: int
    status: PlanStatus
    steps: tuple[PlanStep, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        if self.version < 1:
            raise ValueError("plan version must be positive")
        if not self.steps:
            raise ValueError("plan must contain at least one step")
        positions = tuple(step.position for step in self.steps)
        if positions != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("plan step positions must be consecutive from one")

    @classmethod
    def propose(
        cls,
        *,
        task_id: TaskId,
        version: int,
        steps: tuple[PlanStep, ...],
        plan_id: PlanId | None = None,
        now: datetime | None = None,
    ) -> "Plan":
        return cls(
            id=plan_id or new_plan_id(),
            task_id=task_id,
            version=version,
            status=PlanStatus.PROPOSED,
            steps=steps,
            created_at=now or utc_now(),
        )

    def apply_approval(self, approval: Approval) -> "Plan":
        """Bind one explicit decision to this exact immutable plan version."""

        if (
            approval.task_id != self.task_id
            or approval.plan_id != self.id
            or approval.plan_version != self.version
        ):
            raise ApprovalMismatchError(
                plan_id=str(self.id),
                plan_version=self.version,
                approval_plan_id=str(approval.plan_id),
                approval_plan_version=approval.plan_version,
            )
        status = (
            PlanStatus.APPROVED
            if approval.decision is ApprovalDecision.APPROVED
            else PlanStatus.REJECTED
        )
        return replace(self, status=status)


@dataclass(frozen=True, slots=True)
class Run:
    id: RunId
    task_id: TaskId
    attempt: int
    status: RunStatus
    plan_id: PlanId | None
    plan_version: int | None
    previous_run_id: RunId | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        require_utc(self.updated_at)
        if self.attempt < 1:
            raise ValueError("run attempt must be positive")
        if (self.plan_id is None) != (self.plan_version is None):
            raise ValueError("plan_id and plan_version must be supplied together")
        if self.plan_version is not None and self.plan_version < 1:
            raise ValueError("run plan_version must be positive")

    @classmethod
    def queue(
        cls,
        *,
        task_id: TaskId,
        attempt: int = 1,
        plan_id: PlanId | None = None,
        plan_version: int | None = None,
        previous_run_id: RunId | None = None,
        run_id: RunId | None = None,
        now: datetime | None = None,
    ) -> "Run":
        timestamp = now or utc_now()
        return cls(
            id=run_id or new_run_id(),
            task_id=task_id,
            attempt=attempt,
            status=RunStatus.QUEUED,
            plan_id=plan_id,
            plan_version=plan_version,
            previous_run_id=previous_run_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def with_status(self, status: RunStatus, *, now: datetime | None = None) -> "Run":
        return replace(self, status=status, updated_at=now or utc_now())

    def retry(self, *, run_id: RunId | None = None, now: datetime | None = None) -> "Run":
        if self.status not in {
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.NEEDS_REVISION,
        }:
            raise InvalidRetryError(str(self.id), self.status.value)
        return Run.queue(
            task_id=self.task_id,
            attempt=self.attempt + 1,
            plan_id=self.plan_id,
            plan_version=self.plan_version,
            previous_run_id=self.id,
            run_id=run_id,
            now=now,
        )


@dataclass(frozen=True, slots=True)
class Artifact:
    id: ArtifactId
    task_id: TaskId
    run_id: RunId | None
    kind: str
    uri: str
    sha256: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        if not self.kind.strip() or not self.uri.strip():
            raise ValueError("artifact kind and uri must not be empty")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("artifact sha256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class ModelResolution:
    id: ModelResolutionId
    task_id: TaskId
    run_id: RunId | None
    profile: str
    provider: str
    model: str
    account: str | None
    reason: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        required = (self.profile, self.provider, self.model, self.reason)
        if any(not value.strip() for value in required):
            raise ValueError("model resolution required fields must not be empty")


@dataclass(frozen=True, slots=True)
class TraceLink:
    id: TraceLinkId
    task_id: TaskId
    run_id: RunId | None
    backend: str
    trace_id: str
    url: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at)
        if not self.backend.strip() or not self.trace_id.strip():
            raise ValueError("trace backend and trace_id must not be empty")
