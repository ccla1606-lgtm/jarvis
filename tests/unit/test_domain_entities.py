from datetime import UTC, datetime

import pytest

from jarvis.domain.entities import (
    Approval,
    ApprovalDecision,
    Plan,
    PlanStatus,
    PlanStep,
    Run,
    RunStatus,
)
from jarvis.domain.errors import ApprovalMismatchError, InvalidRetryError
from jarvis.domain.ids import new_plan_id, new_task_id

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def test_approval_binds_exact_immutable_plan_version() -> None:
    task_id = new_task_id()
    plan_id = new_plan_id()
    plan = Plan.propose(
        task_id=task_id,
        plan_id=plan_id,
        version=2,
        steps=(PlanStep(1, "Implement"),),
        now=NOW,
    )
    old_approval = Approval.record(
        task_id=task_id,
        plan_id=plan_id,
        plan_version=1,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="approved older plan",
        now=NOW,
    )

    with pytest.raises(ApprovalMismatchError):
        plan.apply_approval(old_approval)

    assert plan.status is PlanStatus.PROPOSED

    current_approval = Approval.record(
        task_id=task_id,
        plan_id=plan_id,
        plan_version=2,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="approved current plan",
        now=NOW,
    )
    approved = plan.apply_approval(current_approval)

    assert approved.status is PlanStatus.APPROVED
    assert plan.status is PlanStatus.PROPOSED


def test_retry_creates_new_attempt_and_preserves_previous_identity() -> None:
    previous = Run.queue(task_id=new_task_id(), now=NOW).with_status(
        RunStatus.FAILED,
        now=NOW,
    )

    retry = previous.retry(now=NOW)

    assert retry.id != previous.id
    assert retry.attempt == previous.attempt + 1
    assert retry.previous_run_id == previous.id
    assert retry.status is RunStatus.QUEUED
    assert previous.status is RunStatus.FAILED


def test_active_run_cannot_be_retried() -> None:
    active = Run.queue(task_id=new_task_id(), now=NOW).with_status(
        RunStatus.RUNNING,
        now=NOW,
    )

    with pytest.raises(InvalidRetryError):
        active.retry(now=NOW)


def test_plan_requires_consecutive_steps() -> None:
    with pytest.raises(ValueError, match="consecutive"):
        Plan.propose(
            task_id=new_task_id(),
            version=1,
            steps=(PlanStep(2, "Invalid first position"),),
            now=NOW,
        )
