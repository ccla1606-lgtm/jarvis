"""Read-only application queries for task API projections."""

from dataclasses import dataclass

from jarvis.domain.entities import Plan, Run
from jarvis.domain.ids import TaskId
from jarvis.domain.task import Task, TaskTransition
from jarvis.ports.task_repository import TaskRepository


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task: Task
    transitions: tuple[TaskTransition, ...]
    plan: Plan | None
    runs: tuple[Run, ...]


class TaskQueryService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def list_tasks(self, *, limit: int = 100) -> tuple[Task, ...]:
        return self._repository.list_tasks(limit=limit)

    def get(self, task_id: TaskId) -> TaskSnapshot:
        task = self._repository.get_task(task_id)
        return TaskSnapshot(
            task,
            self._repository.list_transitions(task_id),
            self._repository.get_latest_plan_for_task(task_id),
            self._repository.list_runs(task_id),
        )

    def events_after(
        self,
        task_id: TaskId,
        *,
        after_version: int,
    ) -> tuple[TaskTransition, ...]:
        self._repository.get_task(task_id)
        return tuple(
            transition
            for transition in self._repository.list_transitions(task_id)
            if transition.task_version > after_version
        )
