"""Use cases coordinating pure domain rules and repository transactions."""

from dataclasses import dataclass

from jarvis.domain.entities import (
    Approval,
    ApprovalDecision,
    Plan,
    PlanStep,
    Run,
)
from jarvis.domain.errors import EntityNotFoundError
from jarvis.domain.ids import PlanId, RunId, TaskId
from jarvis.domain.task import Task, TaskStatus
from jarvis.ports.task_repository import TaskRepository


@dataclass(frozen=True, slots=True)
class PlanDecisionResult:
    task: Task
    approval: Approval
    run: Run | None


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
        current = self._repository.get_task(task_id)
        current.transition(
            TaskStatus.QUEUED,
            actor=actor,
            reason="validate approval transition",
        )
        plan = self._repository.get_plan(plan_id)
        if plan.task_id != task_id:
            raise EntityNotFoundError("Plan", str(plan_id))
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
        current = self._repository.get_task(task_id)
        current.transition(
            TaskStatus.REJECTED,
            actor=actor,
            reason="validate rejection transition",
        )
        plan = self._repository.get_plan(plan_id)
        if plan.task_id != task_id:
            raise EntityNotFoundError("Plan", str(plan_id))
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
