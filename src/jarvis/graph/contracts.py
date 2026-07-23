"""JSON-serializable contracts owned by the brain layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypedDict

from jarvis.domain.ids import PlanId, TaskId
from jarvis.domain.task import TaskStatus


class BrainRoute(StrEnum):
    FAST = "fast"
    BOUNDED = "bounded"
    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class BrainScope:
    allowed_tools: tuple[str, ...] = ()
    allowed_repositories: tuple[str, ...] = ()
    side_effects_allowed: bool = False

    def __post_init__(self) -> None:
        entries = (*self.allowed_tools, *self.allowed_repositories)
        if any(not value.strip() for value in entries):
            raise ValueError("brain scope entries must not be empty")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("allowed tools must be unique")
        if len(set(self.allowed_repositories)) != len(self.allowed_repositories):
            raise ValueError("allowed repositories must be unique")


@dataclass(frozen=True, slots=True)
class BrainBudget:
    max_graph_steps: int = 12
    max_model_tokens: int = 16_000
    max_wall_time_seconds: float = 60.0
    max_plan_steps: int = 12
    max_route_repairs: int = 1

    def __post_init__(self) -> None:
        if (
            self.max_graph_steps < 1
            or self.max_model_tokens < 1
            or self.max_wall_time_seconds <= 0
            or self.max_plan_steps < 1
            or self.max_route_repairs < 0
        ):
            raise ValueError("brain budgets must be positive and repair cannot be negative")


@dataclass(frozen=True, slots=True)
class BrainRequest:
    task_id: TaskId
    scope: BrainScope = BrainScope()


@dataclass(frozen=True, slots=True)
class ApprovalSignal:
    plan_id: PlanId
    plan_version: int
    approved: bool

    def __post_init__(self) -> None:
        if self.plan_version < 1:
            raise ValueError("approval signal plan_version must be positive")

    def to_json(self) -> dict[str, object]:
        return {
            "plan_id": str(self.plan_id),
            "plan_version": self.plan_version,
            "approved": self.approved,
        }


@dataclass(frozen=True, slots=True)
class BrainResult:
    task_id: TaskId
    task_status: TaskStatus
    route: BrainRoute | None
    answer: str | None
    plan_id: PlanId | None
    plan_version: int | None
    interrupted: bool
    graph_steps_used: int
    model_tokens_used: int


@dataclass(frozen=True, slots=True)
class TriageDecision:
    route: BrainRoute
    rationale: str
    estimated_steps: int
    requires_side_effects: bool

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> TriageDecision:
        try:
            route = BrainRoute(value["route"])
            rationale = value["rationale"]
            estimated_steps = value["estimated_steps"]
            requires_side_effects = value["requires_side_effects"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid triage decision") from error
        if (
            not isinstance(rationale, str)
            or not rationale.strip()
            or not isinstance(estimated_steps, int)
            or isinstance(estimated_steps, bool)
            or estimated_steps < 1
            or not isinstance(requires_side_effects, bool)
        ):
            raise ValueError("invalid triage decision fields")
        return cls(route, rationale, estimated_steps, requires_side_effects)


@dataclass(frozen=True, slots=True)
class ProposedStep:
    position: int
    description: str
    depends_on: tuple[int, ...]
    tools: tuple[str, ...]
    repositories: tuple[str, ...]

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> ProposedStep:
        try:
            position = value["position"]
            description = value["description"]
            depends_on = value["depends_on"]
            tools = value["tools"]
            repositories = value["repositories"]
        except (KeyError, TypeError) as error:
            raise ValueError("invalid proposed step") from error
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or not isinstance(description, str)
            or not isinstance(depends_on, list)
            or not isinstance(tools, list)
            or not isinstance(repositories, list)
            or any(not isinstance(item, int) or isinstance(item, bool) for item in depends_on)
            or any(not isinstance(item, str) for item in (*tools, *repositories))
        ):
            raise ValueError("invalid proposed step fields")
        return cls(
            position,
            description,
            tuple(depends_on),
            tuple(tools),
            tuple(repositories),
        )


@dataclass(frozen=True, slots=True)
class PlanProposal:
    steps: tuple[ProposedStep, ...]

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> PlanProposal:
        raw_steps = value.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("plan proposal requires a steps list")
        return cls(
            tuple(
                ProposedStep.from_json(step) if isinstance(step, dict) else _raise_invalid_step()
                for step in raw_steps
            )
        )


class BrainState(TypedDict, total=False):
    task_id: str
    objective: str
    allowed_tools: list[str]
    allowed_repositories: list[str]
    side_effects_allowed: bool
    started_at: str
    graph_steps_used: int
    model_tokens_used: int
    terminal: bool
    route: str
    triage_rationale: str
    triage_attempts: int
    answer: str
    bounded_task: dict[str, Any]
    plan_id: str
    plan_version: int
    approval_decision: str
    recovery_node: str


def triage_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "route": {"type": "string", "enum": [route.value for route in BrainRoute]},
            "rationale": {"type": "string", "minLength": 1},
            "estimated_steps": {"type": "integer", "minimum": 1},
            "requires_side_effects": {"type": "boolean"},
        },
        "required": [
            "route",
            "rationale",
            "estimated_steps",
            "requires_side_effects",
        ],
        "additionalProperties": False,
    }


def plan_schema(max_steps: int) -> dict[str, Any]:
    step = {
        "type": "object",
        "properties": {
            "position": {"type": "integer", "minimum": 1},
            "description": {"type": "string", "minLength": 1},
            "depends_on": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "uniqueItems": True,
            },
            "tools": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "repositories": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
        },
        "required": [
            "position",
            "description",
            "depends_on",
            "tools",
            "repositories",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": step,
                "minItems": 1,
                "maxItems": max_steps,
            }
        },
        "required": ["steps"],
        "additionalProperties": False,
    }


def _raise_invalid_step() -> ProposedStep:
    raise ValueError("plan step must be an object")
