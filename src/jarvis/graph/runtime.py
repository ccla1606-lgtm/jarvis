"""Direct LangGraph runtime behind a replaceable Jarvis port."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from jarvis.application.task_service import TaskService
from jarvis.domain.ids import PlanId, TaskId
from jarvis.graph.brain import Graph, build_brain_graph
from jarvis.graph.contracts import (
    ApprovalSignal,
    BrainBudget,
    BrainRequest,
    BrainResult,
    BrainRoute,
    BrainState,
)
from jarvis.models.ports import ModelPort
from jarvis.ports.task_repository import TaskRepository


class LangGraphBrainRuntime:
    """Run the brain directly, without LangSmith or Agent Server."""

    def __init__(
        self,
        *,
        repository: TaskRepository,
        models: ModelPort,
        checkpointer: BaseCheckpointSaver[Any],
        budget: BrainBudget | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._now = now or (lambda: datetime.now(UTC))
        self._graph: Graph = build_brain_graph(
            tasks=TaskService(repository),
            repository=repository,
            models=models,
            budget=budget or BrainBudget(),
            checkpointer=checkpointer,
            now=self._now,
        )

    @classmethod
    def local(
        cls,
        *,
        repository: TaskRepository,
        models: ModelPort,
        budget: BrainBudget | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> LangGraphBrainRuntime:
        """Build a dependency-free development runtime with an in-memory projection."""

        return cls(
            repository=repository,
            models=models,
            checkpointer=InMemorySaver(),
            budget=budget,
            now=now,
        )

    async def run(self, request: BrainRequest) -> BrainResult:
        task = self._repository.get_task(request.task_id)
        state: BrainState = {
            "task_id": str(task.id),
            "objective": task.objective,
            "allowed_tools": list(request.scope.allowed_tools),
            "allowed_repositories": list(request.scope.allowed_repositories),
            "side_effects_allowed": request.scope.side_effects_allowed,
            "started_at": self._now().isoformat(),
            "graph_steps_used": 0,
            "model_tokens_used": 0,
        }
        config = _config(task.id)
        await self._graph.ainvoke(state, config)
        return await self._result(task.id, config)

    async def resume(
        self,
        task_id: TaskId,
        signal: ApprovalSignal,
    ) -> BrainResult:
        config = _config(task_id)
        await self._graph.aupdate_state(
            config,
            {"started_at": self._now().isoformat()},
        )
        await self._graph.ainvoke(Command(resume=signal.to_json()), config)
        return await self._result(task_id, config)

    def mermaid(self) -> str:
        return self._graph.get_graph().draw_mermaid()

    async def _result(
        self,
        task_id: TaskId,
        config: RunnableConfig,
    ) -> BrainResult:
        snapshot = await self._graph.aget_state(config)
        state = cast(BrainState, snapshot.values)
        task = self._repository.get_task(task_id)
        route_value = state.get("route")
        plan_value = state.get("plan_id")
        interrupted = any(task.interrupts for task in snapshot.tasks)
        return BrainResult(
            task_id,
            task.status,
            BrainRoute(route_value) if route_value is not None else None,
            state.get("answer"),
            PlanId(UUID(plan_value)) if plan_value is not None else None,
            state.get("plan_version"),
            interrupted,
            state.get("graph_steps_used", 0),
            state.get("model_tokens_used", 0),
        )


def _config(task_id: TaskId) -> RunnableConfig:
    return {"configurable": {"thread_id": str(task_id)}}
