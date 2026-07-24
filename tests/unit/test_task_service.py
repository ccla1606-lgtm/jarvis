from jarvis.application.task_service import TaskService
from jarvis.domain.entities import ApprovalDecision, PlanStatus, PlanStep, Run, RunStatus
from jarvis.domain.task import TaskStatus
from jarvis.infrastructure.memory_repository import InMemoryTaskRepository


def test_service_coordinates_task_plan_approval_and_run() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)

    task = service.submit("Implement M1", idempotency_key="m1")
    triaging = service.transition(
        task.id,
        TaskStatus.TRIAGING,
        actor="brain",
        reason="begin triage",
    )
    planning = service.transition(
        task.id,
        TaskStatus.PLANNING,
        actor="brain",
        reason="complex request",
    )
    plan = service.propose_plan(
        task.id,
        version=1,
        steps=(PlanStep(1, "Implement"), PlanStep(2, "Verify")),
    )
    approval = service.decide_plan(
        plan.id,
        plan_version=1,
        decision=ApprovalDecision.APPROVED,
        actor="operator",
        reason="scope accepted",
    )
    run = service.queue_run(task.id, plan=repository.get_plan(plan.id))

    assert triaging.status is TaskStatus.TRIAGING
    assert planning.status is TaskStatus.PLANNING
    assert approval.plan_id == plan.id
    assert repository.get_plan(plan.id).status is PlanStatus.APPROVED
    assert run.plan_id == plan.id
    assert repository.list_transitions(task.id)[-1].to_status is TaskStatus.PLANNING


def test_service_queues_fast_run_without_plan_and_retries_failure() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)
    task = service.submit("Answer", idempotency_key="answer")
    queued = service.queue_run(task.id)
    failed = queued.with_status(RunStatus.FAILED)

    replacement_repository = InMemoryTaskRepository()
    replacement_service = TaskService(replacement_repository)
    replacement_repository.create_task(task, idempotency_key="answer")
    replacement_repository.create_run(failed)
    retry = replacement_service.retry_run(failed.id)

    assert queued.plan_id is None
    assert retry.previous_run_id == failed.id


def test_run_factory_can_preserve_explicit_failed_attempt() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)
    task = service.submit("Task", idempotency_key="task")
    run = Run.queue(task_id=task.id).with_status(RunStatus.FAILED)

    assert repository.create_run(run) == run


def test_plan_decision_replay_returns_original_approval_and_run() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)
    task = service.submit("Change repository", idempotency_key="decision-replay")
    service.transition(
        task.id,
        TaskStatus.TRIAGING,
        actor="brain",
        reason="triage",
    )
    service.transition(
        task.id,
        TaskStatus.PLANNING,
        actor="brain",
        reason="plan",
    )
    service.transition(
        task.id,
        TaskStatus.AWAITING_APPROVAL,
        actor="brain",
        reason="await approval",
    )
    plan = service.propose_plan(
        task.id,
        version=1,
        steps=(PlanStep(1, "Apply approved change"),),
    )

    first = service.approve_plan(
        task.id,
        plan.id,
        plan_version=plan.version,
        actor="operator",
        reason="approved",
    )
    replay = service.approve_plan(
        task.id,
        plan.id,
        plan_version=plan.version,
        actor="operator",
        reason="approved",
    )

    assert replay.replayed is True
    assert replay.approval == first.approval
    assert replay.run == first.run
    assert len(repository.list_runs(task.id)) == 1


def test_retry_replay_returns_original_attempt() -> None:
    repository = InMemoryTaskRepository()
    service = TaskService(repository)
    task = service.submit("Retry work", idempotency_key="retry-replay")
    service.transition(
        task.id,
        TaskStatus.FAILED,
        actor="executor",
        reason="failed",
    )
    failed = repository.create_run(
        Run.queue(task_id=task.id).with_status(RunStatus.FAILED)
    )

    first = service.retry_task(
        task.id,
        failed.id,
        actor="operator",
        reason="retry",
    )
    replay = service.retry_task(
        task.id,
        failed.id,
        actor="operator",
        reason="retry",
    )

    assert replay.run == first.run
    assert len(repository.list_runs(task.id)) == 2
