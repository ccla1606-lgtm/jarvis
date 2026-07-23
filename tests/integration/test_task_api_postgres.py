from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.application.task_service import TaskService
from jarvis.config import Settings
from jarvis.domain.entities import PlanStep
from jarvis.domain.task import TaskStatus
from jarvis.health import ReadinessResult
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository

pytestmark = pytest.mark.integration
TOKEN = "integration-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@dataclass(frozen=True)
class ReadyProbe:
    def check(self) -> ReadinessResult:
        return ReadinessResult(ready=True, detail="ready")


def _settings(database_url: str, schema: str) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
        database_schema=schema,
        api_token=TOKEN,
    )


def test_api_restart_retains_task_awaiting_approval(
    database_url: str,
    postgres_schema: str,
    postgres_repository: PostgresTaskRepository,
) -> None:
    first_client = TestClient(
        create_app(
            settings=_settings(database_url, postgres_schema),
            readiness_probe=ReadyProbe(),
            repository=postgres_repository,
        )
    )
    submitted = first_client.post(
        "/v1/tasks",
        headers={**AUTH, "Idempotency-Key": "restart-api"},
        json={"objective": "Persist an approval boundary"},
    )
    assert submitted.status_code == 202
    task_id = submitted.json()["task"]["id"]

    service = TaskService(postgres_repository)
    task = postgres_repository.list_tasks(limit=1)[0]
    service.transition(task.id, TaskStatus.TRIAGING, actor="brain", reason="triage")
    service.transition(task.id, TaskStatus.PLANNING, actor="brain", reason="plan")
    plan = service.propose_plan(
        task.id,
        version=1,
        steps=(PlanStep(1, "Wait for approval"),),
    )
    service.transition(
        task.id,
        TaskStatus.AWAITING_APPROVAL,
        actor="brain",
        reason="plan ready",
    )

    restarted_repository = PostgresTaskRepository(database_url, schema=postgres_schema)
    restarted_client = TestClient(
        create_app(
            settings=_settings(database_url, postgres_schema),
            readiness_probe=ReadyProbe(),
            repository=restarted_repository,
        )
    )
    restored = restarted_client.get(f"/v1/tasks/{task_id}", headers=AUTH)

    assert restored.status_code == 200
    assert restored.json()["task"]["status"] == "AWAITING_APPROVAL"
    assert restored.json()["plan"]["id"] == str(plan.id)
    assert restored.json()["plan"]["version"] == 1
    assert restored.json()["runs"] == []
