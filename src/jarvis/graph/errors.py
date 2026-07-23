"""Safe graph orchestration errors."""


class BrainError(RuntimeError):
    """Base error that may cross the runtime boundary."""


class RouteValidationError(BrainError):
    """A model-proposed route violates deterministic policy."""


class PlanValidationError(BrainError):
    """A model-proposed plan is invalid or expands scope."""


class BrainBudgetExceededError(BrainError):
    def __init__(self, budget: str) -> None:
        self.budget = budget
        super().__init__(f"brain {budget} budget exceeded")


class ApprovalResumeError(BrainError):
    """A resume payload does not match committed canonical approval state."""
