"""Versioned HTTP contracts for Jarvis API v1."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jarvis.application.task_queries import TaskSnapshot
from jarvis.domain.entities import Approval, Plan, PlanStep, Run
from jarvis.domain.task import Task, TaskTransition
from jarvis.graph.contracts import BrainResult


class ApiModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ErrorDetail(ApiModel):
    code: str
    message: str
    correlation_id: str


class ErrorResponse(ApiModel):
    error: ErrorDetail


class SubmitTaskRequest(ApiModel):
    objective: str = Field(min_length=1, max_length=20_000)
    allowed_tools: tuple[str, ...] = Field(default=(), max_length=64)
    allowed_repositories: tuple[str, ...] = Field(default=(), max_length=64)
    side_effects_allowed: bool = False

    @field_validator("allowed_tools", "allowed_repositories")
    @classmethod
    def normalize_scope(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("scope entries must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("scope entries must be unique")
        return normalized


class TaskView(ApiModel):
    id: UUID
    objective: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, task: Task) -> Self:
        return cls(
            id=task.id,
            objective=task.objective,
            status=task.status.value,
            version=task.version,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class PlanStepView(ApiModel):
    position: int
    description: str
    depends_on: tuple[int, ...]
    tools: tuple[str, ...]
    repositories: tuple[str, ...]

    @classmethod
    def from_domain(cls, step: PlanStep) -> Self:
        return cls(
            position=step.position,
            description=step.description,
            depends_on=step.depends_on,
            tools=step.tools,
            repositories=step.repositories,
        )


class PlanView(ApiModel):
    id: UUID
    version: int
    status: str
    steps: tuple[PlanStepView, ...]
    created_at: datetime

    @classmethod
    def from_domain(cls, plan: Plan) -> Self:
        return cls(
            id=plan.id,
            version=plan.version,
            status=plan.status.value,
            steps=tuple(PlanStepView.from_domain(step) for step in plan.steps),
            created_at=plan.created_at,
        )


class RunView(ApiModel):
    id: UUID
    attempt: int
    status: str
    plan_id: UUID | None
    plan_version: int | None
    previous_run_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, run: Run) -> Self:
        return cls(
            id=run.id,
            attempt=run.attempt,
            status=run.status.value,
            plan_id=run.plan_id,
            plan_version=run.plan_version,
            previous_run_id=run.previous_run_id,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )


class TransitionView(ApiModel):
    id: UUID
    from_status: str
    to_status: str
    task_version: int
    actor: str
    reason: str
    occurred_at: datetime

    @classmethod
    def from_domain(cls, transition: TaskTransition) -> Self:
        return cls(
            id=transition.id,
            from_status=transition.from_status.value,
            to_status=transition.to_status.value,
            task_version=transition.task_version,
            actor=transition.actor,
            reason=transition.reason,
            occurred_at=transition.occurred_at,
        )


class TaskDetailResponse(ApiModel):
    task: TaskView
    plan: PlanView | None
    runs: tuple[RunView, ...]
    transitions: tuple[TransitionView, ...]

    @classmethod
    def from_snapshot(cls, snapshot: TaskSnapshot) -> Self:
        return cls(
            task=TaskView.from_domain(snapshot.task),
            plan=PlanView.from_domain(snapshot.plan) if snapshot.plan is not None else None,
            runs=tuple(RunView.from_domain(run) for run in snapshot.runs),
            transitions=tuple(
                TransitionView.from_domain(transition) for transition in snapshot.transitions
            ),
        )


class TaskListResponse(ApiModel):
    tasks: tuple[TaskView, ...]


class OrchestrationView(ApiModel):
    route: str | None
    interrupted: bool

    @classmethod
    def from_brain(cls, result: BrainResult | None) -> Self:
        return cls(
            route=result.route.value if result is not None and result.route is not None else None,
            interrupted=result.interrupted if result is not None else False,
        )


class SubmitTaskResponse(ApiModel):
    task: TaskView
    orchestration: OrchestrationView


class PlanDecisionRequest(ApiModel):
    plan_id: UUID
    plan_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class CancelTaskRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=2_000)


class RetryTaskRequest(ApiModel):
    run_id: UUID
    reason: str = Field(min_length=1, max_length=2_000)


class CommandResponse(ApiModel):
    task: TaskView
    approval_id: UUID | None = None
    run_id: UUID | None = None

    @classmethod
    def from_decision(
        cls,
        *,
        task: Task,
        approval: Approval,
        run: Run | None,
    ) -> Self:
        return cls(
            task=TaskView.from_domain(task),
            approval_id=approval.id,
            run_id=run.id if run is not None else None,
        )


class HealthResponse(ApiModel):
    status: Literal["ok", "not_ready"]
    service: str
    detail: str | None = None


class DemoRequest(ApiModel):
    message: str = Field(min_length=1, max_length=2_000)


class DemoResponse(ApiModel):
    task_id: UUID
    status: Literal["accepted"]
    route: Literal["m0_scaffold"]
    message: str
