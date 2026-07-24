"""Thread-safe in-memory repository for unit tests only."""

from threading import Lock

from jarvis.domain.entities import (
    Approval,
    Artifact,
    ModelResolution,
    Plan,
    Run,
    TraceLink,
)
from jarvis.domain.errors import ConcurrencyConflictError, EntityNotFoundError
from jarvis.domain.ids import PlanId, RunId, TaskId
from jarvis.domain.task import Task, TaskTransition


class InMemoryTaskRepository:
    """Deterministic fake implementing the same optimistic rules as PostgreSQL."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[TaskId, Task] = {}
        self._idempotency: dict[str, TaskId] = {}
        self._transitions: dict[TaskId, list[TaskTransition]] = {}
        self._plans: dict[PlanId, Plan] = {}
        self._approvals: dict[object, Approval] = {}
        self._runs: dict[RunId, Run] = {}
        self._artifacts: dict[object, Artifact] = {}
        self._model_resolutions: dict[object, ModelResolution] = {}
        self._trace_links: dict[object, TraceLink] = {}

    def create_task(self, task: Task, *, idempotency_key: str) -> Task:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key must not be empty")
        with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                return self._tasks[existing_id]
            self._tasks[task.id] = task
            self._idempotency[key] = task.id
            self._transitions[task.id] = []
            return task

    def get_task(self, task_id: TaskId) -> Task:
        with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as error:
                raise EntityNotFoundError("Task", str(task_id)) from error

    def list_tasks(self, *, limit: int = 100) -> tuple[Task, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("task list limit must be between 1 and 100")
        with self._lock:
            return tuple(
                sorted(
                    self._tasks.values(),
                    key=lambda task: (task.created_at, str(task.id)),
                    reverse=True,
                )[:limit]
            )

    def save_transition(
        self,
        task: Task,
        transition: TaskTransition,
        *,
        expected_version: int,
    ) -> Task:
        with self._lock:
            try:
                current = self._tasks[task.id]
            except KeyError as error:
                raise EntityNotFoundError("Task", str(task.id)) from error
            if current.version != expected_version:
                raise ConcurrencyConflictError(
                    "Task",
                    str(task.id),
                    expected_version,
                    current.version,
                )
            if task.version != expected_version + 1:
                raise ValueError("saved task must increment expected_version exactly once")
            if (
                transition.task_id != task.id
                or transition.from_status is not current.status
                or transition.to_status is not task.status
                or transition.task_version != task.version
            ):
                raise ValueError("transition does not match the task update")
            self._tasks[task.id] = task
            self._transitions[task.id].append(transition)
            return task

    def list_transitions(self, task_id: TaskId) -> tuple[TaskTransition, ...]:
        with self._lock:
            if task_id not in self._tasks:
                raise EntityNotFoundError("Task", str(task_id))
            return tuple(self._transitions[task_id])

    def create_plan(self, plan: Plan) -> Plan:
        with self._lock:
            if plan.task_id not in self._tasks:
                raise EntityNotFoundError("Task", str(plan.task_id))
            if any(
                stored.task_id == plan.task_id and stored.version == plan.version
                for stored in self._plans.values()
            ):
                raise ValueError(f"plan version {plan.version} already exists")
            self._plans[plan.id] = plan
            return plan

    def get_plan(self, plan_id: PlanId) -> Plan:
        with self._lock:
            try:
                return self._plans[plan_id]
            except KeyError as error:
                raise EntityNotFoundError("Plan", str(plan_id)) from error

    def get_plan_for_task(self, task_id: TaskId, *, version: int) -> Plan | None:
        with self._lock:
            self._require_task(task_id)
            return next(
                (
                    plan
                    for plan in self._plans.values()
                    if plan.task_id == task_id and plan.version == version
                ),
                None,
            )

    def get_latest_plan_for_task(self, task_id: TaskId) -> Plan | None:
        with self._lock:
            self._require_task(task_id)
            plans = tuple(plan for plan in self._plans.values() if plan.task_id == task_id)
            return max(plans, key=lambda plan: plan.version, default=None)

    def record_approval(self, approval: Approval) -> Approval:
        with self._lock:
            plan = self._plans.get(approval.plan_id)
            if plan is None:
                raise EntityNotFoundError("Plan", str(approval.plan_id))
            self._plans[plan.id] = plan.apply_approval(approval)
            self._approvals[approval.id] = approval
            return approval

    def get_approval_for_plan(
        self,
        plan_id: PlanId,
        *,
        plan_version: int,
    ) -> Approval | None:
        with self._lock:
            return next(
                (
                    approval
                    for approval in self._approvals.values()
                    if approval.plan_id == plan_id and approval.plan_version == plan_version
                ),
                None,
            )

    def create_run(self, run: Run) -> Run:
        with self._lock:
            if run.task_id not in self._tasks:
                raise EntityNotFoundError("Task", str(run.task_id))
            if any(
                stored.task_id == run.task_id and stored.attempt == run.attempt
                for stored in self._runs.values()
            ):
                raise ValueError(f"run attempt {run.attempt} already exists")
            self._runs[run.id] = run
            return run

    def get_run(self, run_id: RunId) -> Run:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as error:
                raise EntityNotFoundError("Run", str(run_id)) from error

    def list_runs(self, task_id: TaskId) -> tuple[Run, ...]:
        with self._lock:
            if task_id not in self._tasks:
                raise EntityNotFoundError("Task", str(task_id))
            return tuple(
                sorted(
                    (run for run in self._runs.values() if run.task_id == task_id),
                    key=lambda run: run.attempt,
                )
            )

    def add_artifact(self, artifact: Artifact) -> Artifact:
        with self._lock:
            self._require_task(artifact.task_id)
            self._artifacts[artifact.id] = artifact
            return artifact

    def add_model_resolution(self, resolution: ModelResolution) -> ModelResolution:
        with self._lock:
            self._require_task(resolution.task_id)
            self._model_resolutions[resolution.id] = resolution
            return resolution

    def add_trace_link(self, trace_link: TraceLink) -> TraceLink:
        with self._lock:
            self._require_task(trace_link.task_id)
            self._trace_links[trace_link.id] = trace_link
            return trace_link

    def _require_task(self, task_id: TaskId) -> None:
        if task_id not in self._tasks:
            raise EntityNotFoundError("Task", str(task_id))
