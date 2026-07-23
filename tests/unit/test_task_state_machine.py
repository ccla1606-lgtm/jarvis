from datetime import UTC, datetime
from itertools import product

import pytest

from jarvis.domain.errors import InvalidTransitionError
from jarvis.domain.task import ALLOWED_TASK_TRANSITIONS, Task, TaskStatus

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current, targets in ALLOWED_TASK_TRANSITIONS.items()
        for target in targets
    ],
)
def test_every_declared_transition_succeeds(
    current: TaskStatus,
    target: TaskStatus,
) -> None:
    task = Task(
        id=Task.create("seed", now=NOW).id,
        objective="Build Jarvis",
        status=current,
        version=7,
        created_at=NOW,
        updated_at=NOW,
    )

    updated, evidence = task.transition(
        target,
        actor="test",
        reason="exhaustive transition contract",
        now=NOW,
    )

    assert updated.status is target
    assert updated.version == 8
    assert evidence.from_status is current
    assert evidence.to_status is target
    assert evidence.task_version == updated.version
    assert task.status is current
    assert task.version == 7


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current, target in product(TaskStatus, repeat=2)
        if target not in ALLOWED_TASK_TRANSITIONS[current]
    ],
)
def test_every_undeclared_transition_is_rejected_without_mutation(
    current: TaskStatus,
    target: TaskStatus,
) -> None:
    task = Task(
        id=Task.create("seed", now=NOW).id,
        objective="Build Jarvis",
        status=current,
        version=3,
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(InvalidTransitionError):
        task.transition(
            target,
            actor="test",
            reason="negative transition contract",
            now=NOW,
        )

    assert task.status is current
    assert task.version == 3


def test_transition_matrix_declares_every_state() -> None:
    assert set(ALLOWED_TASK_TRANSITIONS) == set(TaskStatus)
