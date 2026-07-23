from datetime import UTC, datetime, timedelta, timezone

import pytest

from jarvis.domain.entities import (
    Approval,
    ApprovalDecision,
    Artifact,
    ModelResolution,
    Plan,
    PlanStep,
    Run,
    RunStatus,
    TraceLink,
)
from jarvis.domain.errors import (
    ApprovalMismatchError,
    ConcurrencyConflictError,
    EntityNotFoundError,
    InvalidRetryError,
    InvalidTransitionError,
)
from jarvis.domain.ids import (
    new_artifact_id,
    new_model_resolution_id,
    new_plan_id,
    new_run_id,
    new_task_id,
    new_trace_link_id,
    new_transition_id,
)
from jarvis.domain.task import Task, TaskStatus, TaskTransition
from jarvis.domain.time import require_utc

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def test_all_typed_identifier_factories_are_unique() -> None:
    values = {
        new_task_id(),
        new_transition_id(),
        new_plan_id(),
        new_run_id(),
        new_artifact_id(),
        new_model_resolution_id(),
        new_trace_link_id(),
    }
    assert len(values) == 7


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 7, 24, 12),
        datetime(2026, 7, 24, 12, tzinfo=timezone(timedelta(hours=2))),
    ],
)
def test_domain_rejects_non_utc_time(timestamp: datetime) -> None:
    with pytest.raises(ValueError, match="UTC"):
        require_utc(timestamp)


def test_task_and_transition_validate_required_fields() -> None:
    task_id = new_task_id()
    with pytest.raises(ValueError, match="objective"):
        Task(task_id, " ", TaskStatus.RECEIVED, 0, NOW, NOW)
    with pytest.raises(ValueError, match="negative"):
        Task(task_id, "Task", TaskStatus.RECEIVED, -1, NOW, NOW)
    with pytest.raises(ValueError, match="precede"):
        Task(task_id, "Task", TaskStatus.RECEIVED, 0, NOW, NOW - timedelta(seconds=1))

    base = {
        "id": new_transition_id(),
        "task_id": task_id,
        "run_id": None,
        "from_status": TaskStatus.RECEIVED,
        "to_status": TaskStatus.TRIAGING,
        "task_version": 1,
        "actor": "agent",
        "reason": "triage",
        "occurred_at": NOW,
    }
    for field, value, match in (
        ("task_version", 0, "positive"),
        ("actor", " ", "actor"),
        ("reason", " ", "reason"),
    ):
        invalid = dict(base)
        invalid[field] = value
        with pytest.raises(ValueError, match=match):
            TaskTransition(**invalid)


def test_plan_approval_and_run_validate_shape() -> None:
    task_id = new_task_id()
    plan_id = new_plan_id()
    with pytest.raises(ValueError, match="positive"):
        Approval.record(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=0,
            decision=ApprovalDecision.APPROVED,
            actor="operator",
            reason="reason",
            now=NOW,
        )
    with pytest.raises(ValueError, match="actor"):
        Approval.record(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=1,
            decision=ApprovalDecision.APPROVED,
            actor=" ",
            reason="reason",
            now=NOW,
        )
    with pytest.raises(ValueError, match="reason"):
        Approval.record(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=1,
            decision=ApprovalDecision.APPROVED,
            actor="operator",
            reason=" ",
            now=NOW,
        )
    with pytest.raises(ValueError, match="positive"):
        Plan.propose(
            task_id=task_id,
            version=0,
            steps=(PlanStep(1, "Step"),),
            now=NOW,
        )
    with pytest.raises(ValueError, match="at least"):
        Plan.propose(task_id=task_id, version=1, steps=(), now=NOW)
    with pytest.raises(ValueError, match="positive"):
        PlanStep(0, "Step")
    with pytest.raises(ValueError, match="description"):
        PlanStep(1, " ")

    with pytest.raises(ValueError, match="attempt"):
        Run(
            id=new_run_id(),
            task_id=task_id,
            attempt=0,
            status=RunStatus.QUEUED,
            plan_id=None,
            plan_version=None,
            previous_run_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
    with pytest.raises(ValueError, match="together"):
        Run.queue(task_id=task_id, plan_id=plan_id, plan_version=None, now=NOW)
    with pytest.raises(ValueError, match="positive"):
        Run.queue(task_id=task_id, plan_id=plan_id, plan_version=0, now=NOW)


def test_evidence_value_objects_validate_safe_metadata() -> None:
    task_id = new_task_id()
    with pytest.raises(ValueError, match="kind"):
        Artifact(new_artifact_id(), task_id, None, " ", "uri", "a" * 64, NOW)
    with pytest.raises(ValueError, match="sha256"):
        Artifact(new_artifact_id(), task_id, None, "patch", "uri", "BAD", NOW)
    with pytest.raises(ValueError, match="required"):
        ModelResolution(
            new_model_resolution_id(),
            task_id,
            None,
            "coder",
            " ",
            "model",
            None,
            "reason",
            NOW,
        )
    with pytest.raises(ValueError, match="backend"):
        TraceLink(new_trace_link_id(), task_id, None, " ", "trace", None, NOW)


def test_typed_errors_have_actionable_messages() -> None:
    assert "not allowed" in str(InvalidTransitionError("A", "B"))
    assert "expected 1, found 2" in str(ConcurrencyConflictError("Task", "id", 1, 2))
    assert "was not found" in str(EntityNotFoundError("Task", "id"))
    assert "cannot authorize" in str(ApprovalMismatchError("plan", 2, "plan", 1))
    assert "cannot be retried" in str(InvalidRetryError("run", "RUNNING"))
