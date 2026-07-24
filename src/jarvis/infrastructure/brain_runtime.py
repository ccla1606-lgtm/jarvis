"""Durable PostgreSQL composition for the LangGraph runtime projection."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.conninfo import make_conninfo

from jarvis.domain.ids import TaskId
from jarvis.graph.contracts import ApprovalSignal, BrainBudget, BrainRequest, BrainResult
from jarvis.graph.runtime import LangGraphBrainRuntime
from jarvis.infrastructure.migrations import validate_schema_name
from jarvis.models.ports import ModelPort
from jarvis.ports.task_repository import TaskRepository


class BrainRuntimeHandle:
    """Lifecycle-safe proxy used by HTTP handlers while the app owns the runtime."""

    def __init__(self) -> None:
        self._runtime: LangGraphBrainRuntime | None = None

    def bind(self, runtime: LangGraphBrainRuntime) -> None:
        self._runtime = runtime

    def clear(self) -> None:
        self._runtime = None

    async def run(self, request: BrainRequest) -> BrainResult:
        return await self._require_runtime().run(request)

    async def resume(self, task_id: TaskId, signal: ApprovalSignal) -> BrainResult:
        return await self._require_runtime().resume(task_id, signal)

    def mermaid(self) -> str:
        return self._require_runtime().mermaid()

    def _require_runtime(self) -> LangGraphBrainRuntime:
        if self._runtime is None:
            raise RuntimeError("brain runtime is not started")
        return self._runtime


@asynccontextmanager
async def postgres_brain_runtime(
    *,
    database_url: str,
    schema: str,
    repository: TaskRepository,
    models: ModelPort,
    budget: BrainBudget | None = None,
    now: Callable[[], datetime] | None = None,
) -> AsyncIterator[LangGraphBrainRuntime]:
    """Create a direct runtime whose checkpoints survive process restarts."""

    safe_schema = validate_schema_name(schema)
    conninfo = make_conninfo(
        database_url,
        options=f"-c search_path={safe_schema}",
    )
    serializer = JsonPlusSerializer(allowed_msgpack_modules=())
    async with AsyncPostgresSaver.from_conn_string(
        conninfo,
        serde=serializer,
    ) as checkpointer:
        await checkpointer.setup()
        yield LangGraphBrainRuntime(
            repository=repository,
            models=models,
            checkpointer=checkpointer,
            budget=budget or BrainBudget(),
            now=now,
        )
