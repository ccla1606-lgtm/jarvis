"""Persistence port for canonical task-owned state."""

from typing import Protocol

from jarvis.domain.entities import (
    Approval,
    Artifact,
    ModelResolution,
    Plan,
    Run,
    TraceLink,
)
from jarvis.domain.ids import PlanId, RunId, TaskId
from jarvis.domain.task import Task, TaskTransition


class TaskRepository(Protocol):
    """Transaction boundary for the M1 aggregate set."""

    def create_task(self, task: Task, *, idempotency_key: str) -> Task: ...

    def get_task(self, task_id: TaskId) -> Task: ...

    def list_tasks(self, *, limit: int = 100) -> tuple[Task, ...]: ...

    def save_transition(
        self,
        task: Task,
        transition: TaskTransition,
        *,
        expected_version: int,
    ) -> Task: ...

    def list_transitions(self, task_id: TaskId) -> tuple[TaskTransition, ...]: ...

    def create_plan(self, plan: Plan) -> Plan: ...

    def get_plan(self, plan_id: PlanId) -> Plan: ...

    def get_plan_for_task(self, task_id: TaskId, *, version: int) -> Plan | None: ...

    def get_latest_plan_for_task(self, task_id: TaskId) -> Plan | None: ...

    def record_approval(self, approval: Approval) -> Approval: ...

    def get_approval_for_plan(
        self,
        plan_id: PlanId,
        *,
        plan_version: int,
    ) -> Approval | None: ...

    def create_run(self, run: Run) -> Run: ...

    def get_run(self, run_id: RunId) -> Run: ...

    def list_runs(self, task_id: TaskId) -> tuple[Run, ...]: ...

    def add_artifact(self, artifact: Artifact) -> Artifact: ...

    def add_model_resolution(self, resolution: ModelResolution) -> ModelResolution: ...

    def add_trace_link(self, trace_link: TraceLink) -> TraceLink: ...
