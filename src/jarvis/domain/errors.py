"""Typed domain and persistence errors."""


class DomainError(Exception):
    """Base error safe for application-layer classification."""


class InvalidTransitionError(DomainError):
    """The requested state edge is not declared."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target

    def __str__(self) -> str:
        return f"transition {self.current} -> {self.target} is not allowed"


class ConcurrencyConflictError(DomainError):
    """The aggregate changed after the caller read it."""

    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        expected_version: int,
        actual_version: int,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.actual_version = actual_version

    def __str__(self) -> str:
        return (
            f"{self.entity_type} {self.entity_id} version conflict: "
            f"expected {self.expected_version}, found {self.actual_version}"
        )


class EntityNotFoundError(DomainError):
    """A requested canonical entity does not exist."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id

    def __str__(self) -> str:
        return f"{self.entity_type} {self.entity_id} was not found"


class ApprovalMismatchError(DomainError):
    """An approval does not authorize the immutable plan version."""

    def __init__(
        self,
        plan_id: str,
        plan_version: int,
        approval_plan_id: str,
        approval_plan_version: int,
    ) -> None:
        self.plan_id = plan_id
        self.plan_version = plan_version
        self.approval_plan_id = approval_plan_id
        self.approval_plan_version = approval_plan_version

    def __str__(self) -> str:
        return (
            f"approval for {self.approval_plan_id}@{self.approval_plan_version} "
            f"cannot authorize {self.plan_id}@{self.plan_version}"
        )


class InvalidRetryError(DomainError):
    """A run in the current state cannot be retried."""

    def __init__(self, run_id: str, status: str) -> None:
        self.run_id = run_id
        self.status = status

    def __str__(self) -> str:
        return f"run {self.run_id} in state {self.status} cannot be retried"
