from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterable
from typing import Any

import pytest

from jarvis.application.task_service import TaskService
from jarvis.domain.entities import ApprovalDecision
from jarvis.domain.task import TaskStatus
from jarvis.graph.contracts import (
    ApprovalSignal,
    BrainRequest,
    BrainRoute,
    BrainScope,
)
from jarvis.infrastructure.brain_runtime import postgres_brain_runtime
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository
from jarvis.models.contracts import (
    FinishReason,
    ModelProfile,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Resolution,
    StreamEvent,
)

pytestmark = pytest.mark.integration


class ScriptedModel:
    def __init__(self, responses: Iterable[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.calls = 0

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if not self._responses:
            raise AssertionError(f"unexpected model request: {request.request_id}")
        return self._responses.popleft()

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        raise AssertionError(f"unexpected stream request: {request.request_id}")


def _response(
    profile: ModelProfile,
    *,
    structured: dict[str, Any],
) -> ModelResponse:
    return ModelResponse(
        content="",
        structured_data=structured,
        tool_calls=(),
        usage=ModelUsage(2, 1, 3),
        resolution=Resolution(profile, "fake", "fake-model", None, 1),
        finish_reason=FinishReason.STOP,
    )


def test_postgres_checkpoint_resumes_after_runtime_reconstruction(
    database_url: str,
    postgres_schema: str,
    postgres_repository: PostgresTaskRepository,
) -> None:
    service = TaskService(postgres_repository)
    task = service.submit("Change the repository", idempotency_key="brain-postgres")
    models = ScriptedModel(
        (
            _response(
                ModelProfile.FAST,
                structured={
                    "route": BrainRoute.PLANNED.value,
                    "rationale": "requires a change",
                    "estimated_steps": 1,
                    "requires_side_effects": True,
                },
            ),
            _response(
                ModelProfile.PLANNER,
                structured={
                    "steps": [
                        {
                            "position": 1,
                            "description": "Apply the change",
                            "depends_on": [],
                            "tools": ["apply_patch"],
                            "repositories": ["owner/repo"],
                        }
                    ]
                },
            ),
        )
    )
    scope = BrainScope(("apply_patch",), ("owner/repo",), True)

    async def scenario() -> None:
        async with postgres_brain_runtime(
            database_url=database_url,
            schema=postgres_schema,
            repository=postgres_repository,
            models=models,
        ) as first_runtime:
            pending = await first_runtime.run(BrainRequest(task.id, scope))

        assert pending.interrupted
        assert pending.plan_id is not None
        service.decide_plan(
            pending.plan_id,
            plan_version=1,
            decision=ApprovalDecision.APPROVED,
            actor="operator",
            reason="integration approval",
        )
        service.transition(
            task.id,
            TaskStatus.QUEUED,
            actor="operator",
            reason="integration queue",
        )

        async with postgres_brain_runtime(
            database_url=database_url,
            schema=postgres_schema,
            repository=postgres_repository,
            models=models,
        ) as second_runtime:
            resumed = await second_runtime.resume(
                task.id,
                ApprovalSignal(pending.plan_id, 1, True),
            )

        assert resumed.task_status is TaskStatus.QUEUED
        assert not resumed.interrupted
        assert models.calls == 2

    asyncio.run(scenario())
