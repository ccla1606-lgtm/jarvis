"""Explicit LangGraph nodes and edges for the Jarvis decision brain."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from jarvis.application.task_service import TaskService
from jarvis.domain.entities import PlanStatus
from jarvis.domain.ids import PlanId, TaskId
from jarvis.domain.task import TaskStatus
from jarvis.graph.contracts import (
    BrainBudget,
    BrainRoute,
    BrainScope,
    BrainState,
    PlanProposal,
    TriageDecision,
    plan_schema,
    triage_schema,
)
from jarvis.graph.errors import (
    ApprovalResumeError,
    BrainBudgetExceededError,
    RouteValidationError,
)
from jarvis.graph.validation import validate_plan, validate_route
from jarvis.models.contracts import (
    MessageRole,
    ModelMessage,
    ModelProfile,
    ModelRequest,
    ModelResponse,
    OutputSchema,
)
from jarvis.models.ports import ModelPort
from jarvis.ports.task_repository import TaskRepository

Graph = CompiledStateGraph[BrainState, None, BrainState, BrainState]


class BrainNodes:
    def __init__(
        self,
        *,
        tasks: TaskService,
        repository: TaskRepository,
        models: ModelPort,
        budget: BrainBudget,
        now: Callable[[], datetime],
    ) -> None:
        self._tasks = tasks
        self._repository = repository
        self._models = models
        self._budget = budget
        self._now = now

    async def intake(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        task_id = task_id_from_state(state)
        task = self._repository.get_task(task_id)
        if task.status is TaskStatus.RECEIVED:
            task = self._tasks.transition(
                task.id,
                TaskStatus.TRIAGING,
                actor="brain:intake",
                reason="request accepted for triage",
            )

        recovery = "end"
        terminal = False
        if task.status is TaskStatus.TRIAGING:
            recovery = "triage"
        elif task.status is TaskStatus.ANSWERING:
            recovery = "fast_answer"
            update["route"] = BrainRoute.FAST.value
        elif task.status is TaskStatus.PLANNING:
            recovery = "planner"
            update["route"] = BrainRoute.PLANNED.value
        elif task.status is TaskStatus.AWAITING_APPROVAL:
            recovery = "wait_for_approval"
            update["route"] = BrainRoute.PLANNED.value
            existing = self._repository.get_plan_for_task(task.id, version=1)
            if existing is None:
                raise ApprovalResumeError("awaiting-approval task has no persisted plan")
            update["plan_id"] = str(existing.id)
            update["plan_version"] = existing.version
        elif task.status is TaskStatus.QUEUED:
            existing = self._repository.get_plan_for_task(task.id, version=1)
            update["route"] = (
                BrainRoute.PLANNED.value if existing is not None else BrainRoute.BOUNDED.value
            )
            if existing is not None:
                update["plan_id"] = str(existing.id)
                update["plan_version"] = existing.version
            terminal = True
        else:
            terminal = True
        update["terminal"] = terminal
        update["recovery_node"] = recovery
        return update

    async def triage(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        messages: tuple[ModelMessage, ...] = (
            ModelMessage(
                MessageRole.SYSTEM,
                (
                    "Classify the request into fast, bounded, or planned. "
                    "Any side-effecting work must use planned."
                ),
            ),
            ModelMessage(MessageRole.USER, state["objective"]),
        )
        used = state.get("model_tokens_used", 0)
        last_error: RouteValidationError | None = None
        for attempt in range(self._budget.max_route_repairs + 1):
            response = await self._models.invoke(
                ModelRequest(
                    ModelProfile.FAST,
                    messages,
                    max_output_tokens=self._model_output_limit(used, 512),
                    output_schema=OutputSchema("triage_decision", triage_schema()),
                    request_id=f"{state['task_id']}:triage:{attempt + 1}",
                )
            )
            used = self._consume_tokens(used, response)
            try:
                decision = _triage_decision(response)
                validate_route(decision, self._budget)
            except (ValueError, RouteValidationError) as error:
                last_error = RouteValidationError(str(error))
                if attempt >= self._budget.max_route_repairs:
                    raise last_error from error
                messages = (
                    *messages,
                    ModelMessage(
                        MessageRole.USER,
                        (
                            "Repair the route. It must respect side effects and "
                            f"the maximum {self._budget.max_plan_steps} step estimate."
                        ),
                    ),
                )
                continue
            update.update(
                {
                    "route": decision.route.value,
                    "triage_rationale": decision.rationale,
                    "triage_attempts": attempt + 1,
                    "model_tokens_used": used,
                }
            )
            return update
        if last_error is not None:
            raise last_error
        raise RouteValidationError("triage did not produce a route")

    async def enter_answering(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        self._transition_if_needed(
            task_id_from_state(state),
            target=TaskStatus.ANSWERING,
            allowed_current={TaskStatus.TRIAGING},
            actor="brain:route",
            reason="validated fast route",
        )
        return update

    async def fast_answer(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        used = state.get("model_tokens_used", 0)
        response = await self._models.invoke(
            ModelRequest(
                ModelProfile.FAST,
                (ModelMessage(MessageRole.USER, state["objective"]),),
                max_output_tokens=self._model_output_limit(used, 2048),
                request_id=f"{state['task_id']}:fast-answer",
            )
        )
        used = self._consume_tokens(used, response)
        update["answer"] = response.content
        update["model_tokens_used"] = used
        return update

    async def finalize_answer(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        self._transition_if_needed(
            task_id_from_state(state),
            target=TaskStatus.SUCCEEDED,
            allowed_current={TaskStatus.ANSWERING},
            actor="brain:fast-answer",
            reason="fast answer completed",
        )
        update["terminal"] = True
        return update

    async def bounded_task(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        self._transition_if_needed(
            task_id_from_state(state),
            target=TaskStatus.QUEUED,
            allowed_current={TaskStatus.TRIAGING},
            actor="brain:route",
            reason="validated bounded task",
        )
        update["bounded_task"] = {
            "objective": state["objective"],
            "allowed_tools": state.get("allowed_tools", []),
            "allowed_repositories": state.get("allowed_repositories", []),
        }
        update["terminal"] = True
        return update

    async def enter_planning(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        self._transition_if_needed(
            task_id_from_state(state),
            target=TaskStatus.PLANNING,
            allowed_current={TaskStatus.TRIAGING},
            actor="brain:route",
            reason="validated planned route",
        )
        return update

    async def planner(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        task_id = task_id_from_state(state)
        existing = self._repository.get_plan_for_task(task_id, version=1)
        if existing is not None:
            update["plan_id"] = str(existing.id)
            update["plan_version"] = existing.version
            return update

        used = state.get("model_tokens_used", 0)
        scope = _scope_from_state(state)
        response = await self._models.invoke(
            ModelRequest(
                ModelProfile.PLANNER,
                (
                    ModelMessage(
                        MessageRole.SYSTEM,
                        (
                            "Create a finite dependency plan. Use only the explicitly "
                            "allowed tools and repositories."
                        ),
                    ),
                    ModelMessage(
                        MessageRole.USER,
                        json.dumps(
                            {
                                "objective": state["objective"],
                                "allowed_tools": list(scope.allowed_tools),
                                "allowed_repositories": list(scope.allowed_repositories),
                                "side_effects_allowed": scope.side_effects_allowed,
                            },
                            separators=(",", ":"),
                        ),
                    ),
                ),
                max_output_tokens=self._model_output_limit(used, 4096),
                output_schema=OutputSchema(
                    "execution_plan",
                    plan_schema(self._budget.max_plan_steps),
                ),
                request_id=f"{state['task_id']}:plan:1",
            )
        )
        used = self._consume_tokens(used, response)
        proposal = _plan_proposal(response)
        steps = validate_plan(proposal, scope=scope, budget=self._budget)
        plan = self._tasks.propose_plan(task_id, version=1, steps=steps)
        update["plan_id"] = str(plan.id)
        update["plan_version"] = plan.version
        update["model_tokens_used"] = used
        return update

    async def finalize_plan(self, state: BrainState) -> BrainState:
        update = self._enter(state)
        self._transition_if_needed(
            task_id_from_state(state),
            target=TaskStatus.AWAITING_APPROVAL,
            allowed_current={TaskStatus.PLANNING},
            actor="brain:planner",
            reason="finite scoped plan proposed",
        )
        return update

    async def wait_for_approval(self, state: BrainState) -> BrainState:
        raw_signal = interrupt(
            {
                "kind": "plan_approval",
                "task_id": state["task_id"],
                "plan_id": state["plan_id"],
                "plan_version": state["plan_version"],
            }
        )
        update = self._enter(state)
        signal = _approval_signal(raw_signal)
        if signal["plan_id"] != state["plan_id"] or signal["plan_version"] != state["plan_version"]:
            raise ApprovalResumeError("approval signal does not match the interrupted plan")
        plan = self._repository.get_plan(plan_id_from_state(state))
        task = self._repository.get_task(task_id_from_state(state))
        approved = signal["approved"]
        if approved and not (
            plan.status is PlanStatus.APPROVED and task.status is TaskStatus.QUEUED
        ):
            raise ApprovalResumeError("approved plan must be committed before graph resume")
        if not approved and not (
            plan.status is PlanStatus.REJECTED and task.status is TaskStatus.REJECTED
        ):
            raise ApprovalResumeError("rejected plan must be committed before graph resume")
        update["approval_decision"] = "approved" if approved else "rejected"
        update["terminal"] = True
        return update

    def _enter(self, state: BrainState) -> BrainState:
        steps = state.get("graph_steps_used", 0) + 1
        if steps > self._budget.max_graph_steps:
            raise BrainBudgetExceededError("graph-step")
        started_at = datetime.fromisoformat(state["started_at"])
        elapsed = (self._now() - started_at).total_seconds()
        if elapsed > self._budget.max_wall_time_seconds:
            raise BrainBudgetExceededError("wall-time")
        return {"graph_steps_used": steps}

    def _model_output_limit(self, used: int, preferred: int) -> int:
        remaining = self._budget.max_model_tokens - used
        if remaining < 1:
            raise BrainBudgetExceededError("model-token")
        return min(preferred, remaining)

    def _consume_tokens(self, used: int, response: ModelResponse) -> int:
        total = used + response.usage.total_tokens
        if total > self._budget.max_model_tokens:
            raise BrainBudgetExceededError("model-token")
        return total

    def _transition_if_needed(
        self,
        task_id: TaskId,
        *,
        target: TaskStatus,
        allowed_current: set[TaskStatus],
        actor: str,
        reason: str,
    ) -> None:
        current = self._repository.get_task(task_id)
        if current.status is target:
            return
        if current.status not in allowed_current:
            raise RuntimeError(
                f"brain cannot enter {target.value} from persisted {current.status.value}"
            )
        self._tasks.transition(
            task_id,
            target,
            actor=actor,
            reason=reason,
        )


def build_brain_graph(
    *,
    tasks: TaskService,
    repository: TaskRepository,
    models: ModelPort,
    budget: BrainBudget,
    checkpointer: BaseCheckpointSaver[Any],
    now: Callable[[], datetime] | None = None,
) -> Graph:
    nodes = BrainNodes(
        tasks=tasks,
        repository=repository,
        models=models,
        budget=budget,
        now=now or (lambda: datetime.now(UTC)),
    )
    builder = StateGraph(BrainState)
    builder.add_node("intake", nodes.intake)
    builder.add_node("triage", nodes.triage)
    builder.add_node("enter_answering", nodes.enter_answering)
    builder.add_node("fast_answer", nodes.fast_answer)
    builder.add_node("finalize_answer", nodes.finalize_answer)
    builder.add_node("bounded_task", nodes.bounded_task)
    builder.add_node("enter_planning", nodes.enter_planning)
    builder.add_node("planner", nodes.planner)
    builder.add_node("finalize_plan", nodes.finalize_plan)
    builder.add_node("wait_for_approval", nodes.wait_for_approval)

    builder.add_edge(START, "intake")
    builder.add_conditional_edges(
        "intake",
        _recovery_node,
        {
            "triage": "triage",
            "fast_answer": "fast_answer",
            "planner": "planner",
            "wait_for_approval": "wait_for_approval",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "triage",
        _route_node,
        {
            BrainRoute.FAST.value: "enter_answering",
            BrainRoute.BOUNDED.value: "bounded_task",
            BrainRoute.PLANNED.value: "enter_planning",
        },
    )
    builder.add_edge("enter_answering", "fast_answer")
    builder.add_edge("fast_answer", "finalize_answer")
    builder.add_edge("finalize_answer", END)
    builder.add_edge("bounded_task", END)
    builder.add_edge("enter_planning", "planner")
    builder.add_edge("planner", "finalize_plan")
    builder.add_edge("finalize_plan", "wait_for_approval")
    builder.add_edge("wait_for_approval", END)
    return builder.compile(checkpointer=checkpointer, name="jarvis-brain")


def _recovery_node(state: BrainState) -> str:
    return state["recovery_node"]


def _route_node(state: BrainState) -> str:
    return BrainRoute(state["route"]).value


def _triage_decision(response: ModelResponse) -> TriageDecision:
    if response.structured_data is None:
        raise ValueError("triage response has no structured data")
    return TriageDecision.from_json(response.structured_data)


def _plan_proposal(response: ModelResponse) -> PlanProposal:
    if response.structured_data is None:
        raise ValueError("planner response has no structured data")
    return PlanProposal.from_json(response.structured_data)


def _scope_from_state(state: BrainState) -> BrainScope:
    return BrainScope(
        tuple(state.get("allowed_tools", [])),
        tuple(state.get("allowed_repositories", [])),
        state.get("side_effects_allowed", False),
    )


class _ApprovalPayload(TypedDict):
    plan_id: str
    plan_version: int
    approved: bool


def _approval_signal(value: object) -> _ApprovalPayload:
    if not isinstance(value, dict):
        raise ApprovalResumeError("approval resume payload must be an object")
    plan_id = value.get("plan_id")
    plan_version = value.get("plan_version")
    approved = value.get("approved")
    if (
        not isinstance(plan_id, str)
        or not isinstance(plan_version, int)
        or isinstance(plan_version, bool)
        or plan_version < 1
        or not isinstance(approved, bool)
    ):
        raise ApprovalResumeError("approval resume payload is invalid")
    return {
        "plan_id": plan_id,
        "plan_version": plan_version,
        "approved": approved,
    }


def task_id_from_state(state: BrainState) -> TaskId:
    from uuid import UUID

    return TaskId(UUID(state["task_id"]))


def plan_id_from_state(state: BrainState) -> PlanId:
    from uuid import UUID

    return PlanId(UUID(state["plan_id"]))
