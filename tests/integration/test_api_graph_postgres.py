from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.config import Settings
from jarvis.health import ReadinessResult
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository

pytestmark = pytest.mark.integration
TOKEN = "m4-1-integration-token"
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
        model_mode="deterministic",
    )


def test_default_api_runs_fast_and_planned_paths_through_postgres(
    database_url: str,
    postgres_schema: str,
    postgres_repository: PostgresTaskRepository,
) -> None:
    del postgres_repository  # fixture applies the canonical schema
    app = create_app(
        settings=_settings(database_url, postgres_schema),
        readiness_probe=ReadyProbe(),
    )

    with TestClient(app) as client:
        fast = client.post(
            "/v1/tasks",
            headers={**AUTH, "Idempotency-Key": "m4-1-fast"},
            json={"objective": "Explain the Jarvis health endpoint"},
        )
        duplicate = client.post(
            "/v1/tasks",
            headers={**AUTH, "Idempotency-Key": "m4-1-fast"},
            json={"objective": "Explain the Jarvis health endpoint"},
        )

        assert fast.status_code == 202
        assert fast.json()["task"]["status"] == "SUCCEEDED"
        assert fast.json()["orchestration"] == {
            "route": "fast",
            "interrupted": False,
        }
        assert duplicate.json()["task"]["id"] == fast.json()["task"]["id"]
        fast_detail = client.get(
            f"/v1/tasks/{fast.json()['task']['id']}",
            headers=AUTH,
        )
        assert fast_detail.status_code == 200
        assert [
            transition["to_status"]
            for transition in fast_detail.json()["transitions"]
        ] == ["TRIAGING", "ANSWERING", "SUCCEEDED"]

        planned = client.post(
            "/v1/tasks",
            headers={**AUTH, "Idempotency-Key": "m4-1-planned"},
            json={
                "objective": "Change the repository configuration",
                "allowed_tools": ["apply_patch"],
                "allowed_repositories": ["owner/repo"],
                "side_effects_allowed": True,
            },
        )
        assert planned.status_code == 202
        assert planned.json()["task"]["status"] == "AWAITING_APPROVAL"
        assert planned.json()["orchestration"] == {
            "route": "planned",
            "interrupted": True,
        }

        task_id = planned.json()["task"]["id"]
        detail = client.get(f"/v1/tasks/{task_id}", headers=AUTH)
        plan = detail.json()["plan"]
        assert plan["version"] == 1
        assert plan["status"] == "PROPOSED"
        assert plan["steps"][0]["tools"] == ["apply_patch"]
        assert plan["steps"][0]["repositories"] == ["owner/repo"]

        approved = client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=AUTH,
            json={
                "plan_id": plan["id"],
                "plan_version": plan["version"],
                "reason": "M4.1 integration approval",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["task"]["status"] == "QUEUED"
        assert approved.json()["run_id"]
        completed = client.get(f"/v1/tasks/{task_id}", headers=AUTH).json()
        assert completed["plan"]["status"] == "APPROVED"
        assert len(completed["runs"]) == 1

        events = client.get(f"/v1/tasks/{task_id}/events", headers=AUTH)
        cursor = completed["task"]["version"]
        current = client.get(
            f"/v1/tasks/{task_id}/events",
            headers={**AUTH, "Last-Event-ID": str(cursor)},
        )
        assert events.text.count("event: task.transition") == cursor
        assert current.text == ": up-to-date\n\n"


def test_default_api_resumes_an_awaiting_plan_after_restart(
    database_url: str,
    postgres_schema: str,
    postgres_repository: PostgresTaskRepository,
) -> None:
    del postgres_repository
    settings = _settings(database_url, postgres_schema)
    first_app = create_app(settings=settings, readiness_probe=ReadyProbe())
    with TestClient(first_app) as first_client:
        submitted = first_client.post(
            "/v1/tasks",
            headers={**AUTH, "Idempotency-Key": "m4-1-restart"},
            json={
                "objective": "Change the repository after restart",
                "allowed_tools": ["apply_patch"],
                "allowed_repositories": ["owner/repo"],
                "side_effects_allowed": True,
            },
        ).json()
        task_id = submitted["task"]["id"]
        plan = first_client.get(f"/v1/tasks/{task_id}", headers=AUTH).json()["plan"]

    second_app = create_app(settings=settings, readiness_probe=ReadyProbe())
    with TestClient(second_app) as second_client:
        restored = second_client.get(f"/v1/tasks/{task_id}", headers=AUTH)
        assert restored.json()["task"]["status"] == "AWAITING_APPROVAL"
        approved = second_client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=AUTH,
            json={
                "plan_id": plan["id"],
                "plan_version": plan["version"],
                "reason": "approve after process restart",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["task"]["status"] == "QUEUED"
        assert approved.json()["run_id"]
