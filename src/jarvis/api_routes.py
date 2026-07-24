"""Versioned task routes that delegate decisions to application services."""

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr
from starlette.concurrency import run_in_threadpool

from jarvis.api_contracts import (
    CancelTaskRequest,
    CommandResponse,
    ErrorResponse,
    OrchestrationView,
    PlanDecisionRequest,
    RetryTaskRequest,
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskView,
    TransitionView,
)
from jarvis.api_errors import invalid_cursor, require_api_token
from jarvis.application.task_queries import TaskQueryService
from jarvis.application.task_service import TaskService
from jarvis.domain.ids import PlanId, RunId, TaskId
from jarvis.domain.task import TaskTransition
from jarvis.graph.contracts import ApprovalSignal, BrainRequest, BrainScope
from jarvis.ports.brain_runtime import BrainRuntimePort
from jarvis.ports.task_repository import TaskRepository

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


def create_task_router(
    *,
    repository: TaskRepository,
    api_token: SecretStr,
    brain_runtime: BrainRuntimePort | None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/tasks", tags=["tasks"])
    commands = TaskService(repository)
    queries = TaskQueryService(repository)
    bearer = HTTPBearer(auto_error=False)

    def authenticated(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer),
        ],
    ) -> str:
        supplied = credentials.credentials if credentials is not None else None
        return require_api_token(supplied, api_token)

    actor_dependency = Annotated[str, Depends(authenticated)]

    @router.post(
        "",
        response_model=SubmitTaskResponse,
        status_code=202,
        responses=ERROR_RESPONSES,
    )
    async def submit_task(
        body: SubmitTaskRequest,
        actor: actor_dependency,
        idempotency_key: Annotated[
            str,
            Header(alias="Idempotency-Key", min_length=1, max_length=200),
        ],
    ) -> SubmitTaskResponse:
        del actor
        task = await run_in_threadpool(
            commands.submit,
            body.objective,
            idempotency_key=idempotency_key,
        )
        brain_result = None
        if brain_runtime is not None:
            brain_result = await brain_runtime.run(
                BrainRequest(
                    task.id,
                    BrainScope(
                        body.allowed_tools,
                        body.allowed_repositories,
                        body.side_effects_allowed,
                    ),
                )
            )
            task = await run_in_threadpool(repository.get_task, task.id)
        return SubmitTaskResponse(
            task=TaskView.from_domain(task),
            orchestration=OrchestrationView.from_brain(brain_result),
        )

    @router.get(
        "",
        response_model=TaskListResponse,
        responses=ERROR_RESPONSES,
    )
    def list_tasks(
        _actor: actor_dependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> TaskListResponse:
        return TaskListResponse(
            tasks=tuple(TaskView.from_domain(task) for task in queries.list_tasks(limit=limit))
        )

    @router.get(
        "/{task_id}",
        response_model=TaskDetailResponse,
        responses=ERROR_RESPONSES,
    )
    def get_task(task_id: UUID, _actor: actor_dependency) -> TaskDetailResponse:
        return TaskDetailResponse.from_snapshot(queries.get(TaskId(task_id)))

    @router.post(
        "/{task_id}/approve",
        response_model=CommandResponse,
        responses=ERROR_RESPONSES,
    )
    async def approve_task(
        task_id: UUID,
        body: PlanDecisionRequest,
        actor: actor_dependency,
    ) -> CommandResponse:
        task_key = TaskId(task_id)
        result = await run_in_threadpool(
            commands.approve_plan,
            task_key,
            PlanId(body.plan_id),
            plan_version=body.plan_version,
            actor=actor,
            reason=body.reason,
        )
        if brain_runtime is not None:
            await brain_runtime.resume(
                task_key,
                ApprovalSignal(PlanId(body.plan_id), body.plan_version, True),
            )
        return CommandResponse.from_decision(
            task=result.task,
            approval=result.approval,
            run=result.run,
        )

    @router.post(
        "/{task_id}/reject",
        response_model=CommandResponse,
        responses=ERROR_RESPONSES,
    )
    async def reject_task(
        task_id: UUID,
        body: PlanDecisionRequest,
        actor: actor_dependency,
    ) -> CommandResponse:
        task_key = TaskId(task_id)
        result = await run_in_threadpool(
            commands.reject_plan,
            task_key,
            PlanId(body.plan_id),
            plan_version=body.plan_version,
            actor=actor,
            reason=body.reason,
        )
        if brain_runtime is not None:
            await brain_runtime.resume(
                task_key,
                ApprovalSignal(PlanId(body.plan_id), body.plan_version, False),
            )
        return CommandResponse.from_decision(
            task=result.task,
            approval=result.approval,
            run=None,
        )

    @router.post(
        "/{task_id}/cancel",
        response_model=CommandResponse,
        responses=ERROR_RESPONSES,
    )
    def cancel_task(
        task_id: UUID,
        body: CancelTaskRequest,
        actor: actor_dependency,
    ) -> CommandResponse:
        task = commands.cancel(
            TaskId(task_id),
            actor=actor,
            reason=body.reason,
        )
        return CommandResponse(task=TaskView.from_domain(task))

    @router.post(
        "/{task_id}/retry",
        response_model=CommandResponse,
        responses=ERROR_RESPONSES,
    )
    def retry_task(
        task_id: UUID,
        body: RetryTaskRequest,
        actor: actor_dependency,
    ) -> CommandResponse:
        result = commands.retry_task(
            TaskId(task_id),
            RunId(body.run_id),
            actor=actor,
            reason=body.reason,
        )
        return CommandResponse(
            task=TaskView.from_domain(result.task),
            run_id=result.run.id,
        )

    @router.get(
        "/{task_id}/events",
        response_class=StreamingResponse,
        responses=ERROR_RESPONSES,
    )
    def task_events(
        task_id: UUID,
        _actor: actor_dependency,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
        after_version: Annotated[int, Query(ge=0)] = 0,
    ) -> StreamingResponse:
        cursor = _event_cursor(last_event_id, after_version)
        transitions = queries.events_after(TaskId(task_id), after_version=cursor)
        body = _sse_body(transitions)
        return StreamingResponse(
            iter((body,)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def _event_cursor(last_event_id: str | None, after_version: int) -> int:
    if last_event_id is None:
        return after_version
    try:
        parsed = int(last_event_id)
    except ValueError as error:
        raise invalid_cursor() from error
    if parsed < 0:
        raise invalid_cursor()
    return max(parsed, after_version)


def _sse_body(transitions: tuple[TaskTransition, ...]) -> str:
    if not transitions:
        return ": up-to-date\n\n"
    chunks: list[str] = []
    for raw_transition in transitions:
        transition = TransitionView.from_domain(raw_transition)
        data = json.dumps(transition.model_dump(mode="json"), separators=(",", ":"))
        chunks.append(f"id: {transition.task_version}\nevent: task.transition\ndata: {data}\n\n")
    return "".join(chunks)
