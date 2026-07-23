from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from jarvis.application.task_service import TaskService
from jarvis.domain.entities import ApprovalDecision, PlanStatus
from jarvis.domain.task import Task, TaskStatus
from jarvis.graph.contracts import (
    ApprovalSignal,
    BrainBudget,
    BrainRequest,
    BrainRoute,
    BrainScope,
)
from jarvis.graph.errors import (
    BrainBudgetExceededError,
    PlanValidationError,
    RouteValidationError,
)
from jarvis.graph.runtime import LangGraphBrainRuntime
from jarvis.infrastructure.memory_repository import InMemoryTaskRepository
from jarvis.models.contracts import (
    FinishReason,
    ModelProfile,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Resolution,
    StreamEvent,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class ScriptedModel:
    def __init__(self, responses: Iterable[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[ModelRequest] = []

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("unexpected model invocation")
        return self._responses.popleft()

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        raise AssertionError(f"unexpected streaming request: {request.request_id}")


def model_response(
    *,
    profile: ModelProfile,
    structured: dict[str, Any] | None = None,
    content: str = "",
    tokens: int = 3,
) -> ModelResponse:
    return ModelResponse(
        content=content,
        structured_data=structured,
        tool_calls=(),
        usage=ModelUsage(tokens - 1, 1, tokens),
        resolution=Resolution(profile, "fake", "fake-model", None, 1),
        finish_reason=FinishReason.STOP,
    )


def triage_response(
    route: str,
    *,
    estimated_steps: int = 1,
    side_effects: bool = False,
) -> ModelResponse:
    return model_response(
        profile=ModelProfile.FAST,
        structured={
            "route": route,
            "rationale": "deterministic fixture",
            "estimated_steps": estimated_steps,
            "requires_side_effects": side_effects,
        },
    )


def plan_response(steps: list[dict[str, Any]]) -> ModelResponse:
    return model_response(
        profile=ModelProfile.PLANNER,
        structured={"steps": steps},
        tokens=7,
    )


def plan_step(
    position: int,
    *,
    depends_on: list[int] | None = None,
    tools: list[str] | None = None,
    repositories: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "position": position,
        "description": f"Step {position}",
        "depends_on": depends_on or [],
        "tools": tools or [],
        "repositories": repositories or [],
    }


def submitted(
    objective: str = "Help me",
) -> tuple[InMemoryTaskRepository, TaskService, Task]:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)
    task = service.submit(objective, idempotency_key=f"submit:{objective}")
    return repository, service, task


def test_simple_request_uses_fast_path_without_plan_or_approval() -> None:
    repository, _service, task = submitted("What time is it?")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.FAST.value),
            model_response(profile=ModelProfile.FAST, content="It is noon."),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        now=lambda: NOW,
    )

    result = asyncio.run(runtime.run(BrainRequest(task.id)))

    assert result.task_status is TaskStatus.SUCCEEDED
    assert result.route is BrainRoute.FAST
    assert result.answer == "It is noon."
    assert result.plan_id is None
    assert not result.interrupted
    assert repository.get_plan_for_task(task.id, version=1) is None
    assert [transition.to_status for transition in repository.list_transitions(task.id)] == [
        TaskStatus.TRIAGING,
        TaskStatus.ANSWERING,
        TaskStatus.SUCCEEDED,
    ]


def test_complex_side_effecting_request_creates_scoped_plan_and_interrupts() -> None:
    repository, _service, task = submitted("Change the repository")
    models = ScriptedModel(
        (
            triage_response(
                BrainRoute.PLANNED.value,
                estimated_steps=2,
                side_effects=True,
            ),
            plan_response(
                [
                    plan_step(1, repositories=["owner/repo"]),
                    plan_step(
                        2,
                        depends_on=[1],
                        tools=["apply_patch"],
                        repositories=["owner/repo"],
                    ),
                ]
            ),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        now=lambda: NOW,
    )

    result = asyncio.run(
        runtime.run(
            BrainRequest(
                task.id,
                BrainScope(
                    allowed_tools=("apply_patch",),
                    allowed_repositories=("owner/repo",),
                    side_effects_allowed=True,
                ),
            )
        )
    )

    assert result.task_status is TaskStatus.AWAITING_APPROVAL
    assert result.route is BrainRoute.PLANNED
    assert result.interrupted
    assert result.plan_id is not None
    plan = repository.get_plan(result.plan_id)
    assert plan.status is PlanStatus.PROPOSED
    assert plan.steps[1].depends_on == (1,)
    assert plan.steps[1].tools == ("apply_patch",)


def test_approval_resume_requires_committed_exact_plan_state() -> None:
    repository, service, task = submitted("Change the repository")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.PLANNED.value, side_effects=True),
            plan_response([plan_step(1, tools=["apply_patch"], repositories=["owner/repo"])]),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        now=lambda: NOW,
    )
    pending = asyncio.run(
        runtime.run(
            BrainRequest(
                task.id,
                BrainScope(("apply_patch",), ("owner/repo",), True),
            )
        )
    )
    assert pending.plan_id is not None
    service.decide_plan(
        pending.plan_id,
        plan_version=1,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="approved in test",
    )
    service.transition(
        task.id,
        TaskStatus.QUEUED,
        actor="operator",
        reason="approved plan queued",
    )

    resumed = asyncio.run(
        runtime.resume(
            task.id,
            ApprovalSignal(pending.plan_id, 1, True),
        )
    )

    assert resumed.task_status is TaskStatus.QUEUED
    assert not resumed.interrupted
    assert len(models.requests) == 2


def test_invalid_semantic_route_gets_exactly_one_repair() -> None:
    repository, _service, task = submitted("Change a file")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.FAST.value, side_effects=True),
            triage_response(BrainRoute.PLANNED.value, side_effects=True),
            plan_response([plan_step(1, tools=["apply_patch"], repositories=["owner/repo"])]),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        budget=BrainBudget(max_route_repairs=1),
        now=lambda: NOW,
    )

    result = asyncio.run(
        runtime.run(
            BrainRequest(
                task.id,
                BrainScope(("apply_patch",), ("owner/repo",), True),
            )
        )
    )

    assert result.interrupted
    assert len(models.requests) == 3
    assert "Repair the route" in models.requests[1].messages[-1].content


def test_invalid_route_stops_after_repair_limit() -> None:
    repository, _service, task = submitted("Change a file")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.FAST.value, side_effects=True),
            triage_response(BrainRoute.BOUNDED.value, side_effects=True),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        budget=BrainBudget(max_route_repairs=1),
        now=lambda: NOW,
    )

    with pytest.raises(RouteValidationError):
        asyncio.run(runtime.run(BrainRequest(task.id)))

    assert len(models.requests) == 2
    assert repository.get_task(task.id).status is TaskStatus.TRIAGING


@pytest.mark.parametrize(
    "steps",
    (
        [plan_step(1, depends_on=[2])],
        [plan_step(1, depends_on=[2]), plan_step(2, depends_on=[1])],
        [plan_step(2)],
        [plan_step(1, tools=["shell"])],
        [plan_step(1, repositories=["other/repo"])],
    ),
)
def test_invalid_or_scope_expanding_plan_is_rejected(
    steps: list[dict[str, Any]],
) -> None:
    repository, _service, task = submitted("Plan invalid work")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.PLANNED.value, side_effects=True),
            plan_response(steps),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        now=lambda: NOW,
    )

    with pytest.raises(PlanValidationError):
        asyncio.run(
            runtime.run(
                BrainRequest(
                    task.id,
                    BrainScope(("apply_patch",), ("owner/repo",), True),
                )
            )
        )

    assert repository.get_plan_for_task(task.id, version=1) is None


def test_plan_step_budget_is_enforced() -> None:
    repository, _service, task = submitted("Too many steps")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.PLANNED.value),
            plan_response([plan_step(1), plan_step(2, depends_on=[1])]),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        budget=BrainBudget(max_plan_steps=1),
        now=lambda: NOW,
    )

    with pytest.raises(PlanValidationError, match="step budget"):
        asyncio.run(runtime.run(BrainRequest(task.id)))


def test_graph_step_and_model_token_budgets_stop_execution() -> None:
    repository, _service, task = submitted("Step budget")
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=ScriptedModel((triage_response(BrainRoute.FAST.value),)),
        budget=BrainBudget(max_graph_steps=1),
        now=lambda: NOW,
    )
    with pytest.raises(BrainBudgetExceededError, match="graph-step"):
        asyncio.run(runtime.run(BrainRequest(task.id)))

    repository2, _service2, task2 = submitted("Token budget")
    runtime2 = LangGraphBrainRuntime.local(
        repository=repository2,
        models=ScriptedModel((triage_response(BrainRoute.FAST.value),)),
        budget=BrainBudget(max_model_tokens=2),
        now=lambda: NOW,
    )
    with pytest.raises(BrainBudgetExceededError, match="model-token"):
        asyncio.run(runtime2.run(BrainRequest(task2.id)))


def test_wall_time_budget_stops_before_model_call() -> None:
    repository, _service, task = submitted("Wall time")
    times = iter((NOW, NOW + timedelta(seconds=2)))
    models = ScriptedModel(())
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        budget=BrainBudget(max_wall_time_seconds=1),
        now=lambda: next(times),
    )

    with pytest.raises(BrainBudgetExceededError, match="wall-time"):
        asyncio.run(runtime.run(BrainRequest(task.id)))

    assert not models.requests


def test_replaying_completed_thread_uses_checkpoint_without_second_model_call() -> None:
    repository, _service, task = submitted("Replay")
    models = ScriptedModel(
        (
            triage_response(BrainRoute.FAST.value),
            model_response(profile=ModelProfile.FAST, content="answer"),
        )
    )
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=models,
        now=lambda: NOW,
    )
    first = asyncio.run(runtime.run(BrainRequest(task.id)))
    second = asyncio.run(runtime.run(BrainRequest(task.id)))

    assert first.answer == second.answer == "answer"
    assert len(models.requests) == 2


def test_direct_runtime_and_mermaid_do_not_require_langsmith(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "LANGSMITH_API_KEY",
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
    ):
        monkeypatch.delenv(name, raising=False)
    repository, _service, task = submitted("No LangSmith")
    runtime = LangGraphBrainRuntime.local(
        repository=repository,
        models=ScriptedModel(
            (
                triage_response(BrainRoute.FAST.value),
                model_response(profile=ModelProfile.FAST, content="answer"),
            )
        ),
        now=lambda: NOW,
    )

    result = asyncio.run(runtime.run(BrainRequest(task.id)))
    mermaid = runtime.mermaid()

    assert result.task_status is TaskStatus.SUCCEEDED
    assert "triage" in mermaid
    assert "wait_for_approval" in mermaid
