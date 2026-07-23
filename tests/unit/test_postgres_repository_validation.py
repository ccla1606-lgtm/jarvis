from dataclasses import replace
from datetime import UTC, datetime

import pytest

from jarvis.domain.task import Task, TaskStatus
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def test_postgres_repository_rejects_unsafe_schema_without_connecting() -> None:
    with pytest.raises(ValueError, match="schema"):
        PostgresTaskRepository("postgresql://unused", schema="bad-name")


def test_postgres_repository_validates_commands_before_connecting() -> None:
    repository = PostgresTaskRepository("postgresql://unused")
    task = Task.create("Task", now=NOW)
    updated, transition = task.transition(
        TaskStatus.TRIAGING,
        actor="agent",
        reason="test",
        now=NOW,
    )

    with pytest.raises(ValueError, match="idempotency"):
        repository.create_task(task, idempotency_key=" ")
    with pytest.raises(ValueError, match="increment"):
        repository.save_transition(
            replace(updated, version=2),
            transition,
            expected_version=task.version,
        )
    with pytest.raises(ValueError, match="does not match"):
        repository.save_transition(
            updated,
            replace(transition, task_version=99),
            expected_version=task.version,
        )
