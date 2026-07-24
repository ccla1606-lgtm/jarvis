"""Use cases coordinating pure domain rules and repository transactions."""

from dataclasses import dataclass

from jarvis.domain.entities import (
    Approval,
    ApprovalDecision,
    Plan,
    PlanStep,
    Run,
)
from jarvis.domain.errors import EntityNotFoundError, InvalidTransitionError
from jarvis.domain.ids import PlanId, RunId, TaskId
from jarvis.domain.task import Task, TaskStatus
from jarvis.ports.task_repository import TaskRepository


@dataclass(frozen=True, slots=True)
class PlanDecisionResult:
    task: Task
    approval: Approval
    run: Run | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class RetryResult:
    task: Task
    run: Run


class TaskService:
    """Thin application layer with no provider, graph, or web dependencies."""

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def submit(self, objective: str, *, idempotency_key: str) -> Task:
        task = Task.create(objective)
        return self._repository.create_task(task, idempotency_key=idempotency_key)

    def transition(
        self,
        task_id: TaskId,
        target: TaskStatus,
        *,
        actor: str,
        reason: str,
        run_id: RunId | None = None,
    ) -> Task:
        current = self._repository.get_task(task_id)
        updated, evidence = current.transition(
            target,
            actor=actor,
            reason=reason,
            run_id=run_id,
        )
        return self._repository.save_transition(
            updated,
            evidence,
            expected_version=current.version,
        )

    def propose_plan(
        self,
        task_id: TaskId,
        *,
        version: int,
        steps: tuple[PlanStep, ...],
    ) -> Plan:
        self._repository.get_task(task_id)
        return self._repository.create_plan(
            Plan.propose(task_id=task_id, version=version, steps=steps)
        )

    def decide_plan(
        self,
        plan_id: PlanId,
        *,
        plan_version: int,
        decision: ApprovalDecision,
        actor: str,
        reason: str,
    ) -> Approval:
        plan = self._repository.get_plan(plan_id)
        approval = Approval.record(
            task_id=plan.task_id,
            plan_id=plan.id,
            plan_version=plan_version,
            decision=decision,
            actor=actor,
            reason=reason,
        )
        return self._repository.record_approval(approval)

    def queue_run(self, task_id: TaskId, *, plan: Plan | None = None) -> Run:
        self._repository.get_task(task_id)
        run = Run.queue(
            task_id=task_id,
            plan_id=plan.id if plan is not None else None,
            plan_version=plan.version if plan is not None else None,
        )
        return self._repository.create_run(run)

    def retry_run(self, run_id: RunId) -> Run:
        previous = self._repository.get_run(run_id)
        retry = previous.retry()
        return self._repository.create_run(retry)

    def approve_plan(
        self,
        task_id: TaskId,
        plan_id: PlanId,
        *,
        plan_version: int,
        actor: str,
        reason: str,
    ) -> PlanDecisionResult:
        plan = self._repository.get_plan(plan_id)
        if plan.task_id != task_id:
            raise EntityNotFoundError("Plan", str(plan_id))
        existing = self._repository.get_approval_for_plan(
            plan_id,
            plan_version=plan_version,
        )
        if existing is not None:
            if existing.decision is not ApprovalDecision.APPROVED:
                raise InvalidTransitionError(plan.status.value, ApprovalDecision.APPROVED.value)
            run = next(
                (
                    candidate
                    for candidate in self._repository.list_runs(task_id)
                    if candidate.plan_id == plan_id
                    and candidate.plan_version == plan_version
                    and candidate.previous_run_id is None
                ),
                None,
            )
            if run is None:
                raise RuntimeError("approved plan has no persisted initial run")
            return PlanDecisionResult(
                self._repository.get_task(task_id),
                existing,
                run,
                replayed=True,
            )

        current = self._repository.get_task(task_id)
        current.transition(
            TaskStatus.QUEUED,
            actor=actor,
            reason="validate approval transition",
        )
        approval = self.decide_plan(
            plan_id,
            plan_version=plan_version,
            decision=ApprovalDecision.APPROVED,
            actor=actor,
            reason=reason,
        )
        task = self.transition(
            task_id,
            TaskStatus.QUEUED,
            actor=actor,
            reason="approved plan queued",
        )
        decided_plan = self._repository.get_plan(plan_id)
        run = self.queue_run(task_id, plan=decided_plan)
        return PlanDecisionResult(task, approval, run)

    def reject_plan(
        self,
        task_id: TaskId,
        plan_id: PlanId,
        *,
        plan_version: int,
        actor: str,
        reason: str,
    ) -> PlanDecisionResult:
        plan = self._repository.get_plan(plan_id)
        if plan.task_id != task_id:
            raise EntityNotFoundError("Plan", str(plan_id))
        existing = self._repository.get_approval_for_plan(
            plan_id,
            plan_version=plan_version,
        )
        if existing is not None:
            if existing.decision is not ApprovalDecision.REJECTED:
                raise InvalidTransitionError(plan.status.value, ApprovalDecision.REJECTED.value)
            return PlanDecisionResult(
                self._repository.get_task(task_id),
                existing,
                None,
                replayed=True,
            )

        current = self._repository.get_task(task_id)
        current.transition(
            TaskStatus.REJECTED,
            actor=actor,
            reason="validate rejection transition",
        )
        approval = self.decide_plan(
            plan_id,
            plan_version=plan_version,
            decision=ApprovalDecision.REJECTED,
            actor=actor,
            reason=reason,
        )
        task = self.transition(
            task_id,
            TaskStatus.REJECTED,
            actor=actor,
            reason="plan rejected",
        )
        return PlanDecisionResult(task, approval, None)

    def cancel(
        self,
        task_id: TaskId,
        *,
        actor: str,
        reason: str,
    ) -> Task:
        current = self._repository.get_task(task_id)
        if current.status is TaskStatus.CANCELLED:
            return current
        return self.transition(
            task_id,
            TaskStatus.CANCELLED,
            actor=actor,
            reason=reason,
        )

    def retry_task(
        self,
        task_id: TaskId,
        run_id: RunId,
        *,
        actor: str,
        reason: str,
    ) -> RetryResult:
        previous = self._repository.get_run(run_id)
        if previous.task_id != task_id:
            raise EntityNotFoundError("Run", str(run_id))
        existing = next(
            (
                candidate
                for candidate in self._repository.list_runs(task_id)
                if candidate.previous_run_id == run_id
            ),
            None,
        )
        if existing is not None:
            return RetryResult(self._repository.get_task(task_id), existing)

        retry = previous.retry()
        current = self._repository.get_task(task_id)
        task = (
            current
            if current.status is TaskStatus.QUEUED
            else self.transition(
                task_id,
                TaskStatus.QUEUED,
                actor=actor,
                reason=reason,
            )
        )
        return RetryResult(task, self._repository.create_run(retry))
