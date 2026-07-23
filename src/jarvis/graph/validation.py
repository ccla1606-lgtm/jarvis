"""Deterministic validation for model-proposed routes and plans."""

from jarvis.domain.entities import PlanStep
from jarvis.graph.contracts import (
    BrainBudget,
    BrainRoute,
    BrainScope,
    PlanProposal,
    TriageDecision,
)
from jarvis.graph.errors import PlanValidationError, RouteValidationError


def validate_route(decision: TriageDecision, budget: BrainBudget) -> None:
    if decision.estimated_steps > budget.max_plan_steps:
        raise RouteValidationError("triage estimate exceeds the configured step budget")
    if decision.requires_side_effects and decision.route is not BrainRoute.PLANNED:
        raise RouteValidationError("side-effecting work requires the planned route")
    if decision.route is BrainRoute.FAST and decision.estimated_steps != 1:
        raise RouteValidationError("fast route must be a single-step answer")


def validate_plan(
    proposal: PlanProposal,
    *,
    scope: BrainScope,
    budget: BrainBudget,
) -> tuple[PlanStep, ...]:
    if not proposal.steps:
        raise PlanValidationError("plan must contain at least one step")
    if len(proposal.steps) > budget.max_plan_steps:
        raise PlanValidationError("plan exceeds the configured step budget")
    allowed_tools = set(scope.allowed_tools)
    allowed_repositories = set(scope.allowed_repositories)
    try:
        steps = tuple(
            PlanStep(
                step.position,
                step.description,
                step.depends_on,
                step.tools,
                step.repositories,
            )
            for step in proposal.steps
        )
    except ValueError as error:
        raise PlanValidationError(str(error)) from error
    _validate_dependencies(steps)
    unknown_tools = {tool for step in steps for tool in step.tools if tool not in allowed_tools}
    unknown_repositories = {
        repository
        for step in steps
        for repository in step.repositories
        if repository not in allowed_repositories
    }
    if unknown_tools or unknown_repositories:
        raise PlanValidationError("plan expands beyond the approved tool or repository scope")
    if not scope.side_effects_allowed and any(step.tools for step in steps):
        raise PlanValidationError("plan requests tools while side effects are disabled")
    return steps


def _validate_dependencies(steps: tuple[PlanStep, ...]) -> None:
    positions = tuple(step.position for step in steps)
    if positions != tuple(range(1, len(steps) + 1)):
        raise PlanValidationError("plan positions must be consecutive from one")
    dependencies = {step.position: step.depends_on for step in steps}
    known = set(positions)
    if any(dependency not in known for values in dependencies.values() for dependency in values):
        raise PlanValidationError("plan dependency references a missing step")

    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(position: int) -> None:
        if position in visiting:
            raise PlanValidationError("plan dependencies contain a cycle")
        if position in visited:
            return
        visiting.add(position)
        for dependency in dependencies[position]:
            visit(dependency)
        visiting.remove(position)
        visited.add(position)

    for position in positions:
        visit(position)
