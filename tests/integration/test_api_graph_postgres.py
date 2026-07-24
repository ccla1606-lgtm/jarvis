from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.application.task_service import TaskService
from jarvis.config import Settings
from jarvis.domain.entities import Run, RunStatus
from jarvis.domain.task import TaskStatus
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


def _submit_planned(client: TestClient, *, key: str, objective: str) -> dict[str, Any]:
    response = client.post(
        "/v1/tasks",
        headers={**AUTH, "Idempotency-Key": key},
        json={
            "objective": objective,
            "allowed_tools": ["apply_patch"],
            "allowed_repositories": ["owner/repo"],
            "side_effects_allowed": True,
        },
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["task"]["status"] == "AWAITING_APPROVAL"
    assert payload["orchestration"] == {"route": "planned", "interrupted": True}
    return payload


def test_default_api_runs_fast_and_approval_paths_through_postgres(
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
        assert [transition["to_status"] for transition in fast_detail.json()["transitions"]] == [
            "TRIAGING",
            "ANSWERING",
            "SUCCEEDED",
        ]

        planned = _submit_planned(
            client,
            key="m4-1-planned",
            objective="Change the repository configuration",
        )
        task_id = planned["task"]["id"]
        detail = client.get(f"/v1/tasks/{task_id}", headers=AUTH)
        plan = detail.json()["plan"]
        assert plan["version"] == 1
        assert plan["status"] == "PROPOSED"
        assert plan["steps"][0]["tools"] == ["apply_patch"]
        assert plan["steps"][0]["repositories"] == ["owner/repo"]

        decision = {
            "plan_id": plan["id"],
            "plan_version": plan["version"],
            "reason": "M4.1 integration approval",
        }
        approved = client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=AUTH,
            json=decision,
        )
        duplicate_approval = client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=AUTH,
            json=decision,
        )
        assert approved.status_code == 200
        assert duplicate_approval.status_code == 200
        assert duplicate_approval.json() == approved.json()
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


def test_default_api_reject_cancel_and_retry_are_idempotent(
    database_url: str,
    postgres_schema: str,
    postgres_repository: PostgresTaskRepository,
) -> None:
    app = create_app(
        settings=_settings(database_url, postgres_schema),
        readiness_probe=ReadyProbe(),
    )
    with TestClient(app) as client:
        rejected_task = _submit_planned(
            client,
            key="m4-1-reject",
            objective="Delete obsolete repository configuration",
        )
        rejected_id = rejected_task["task"]["id"]
        rejected_plan = client.get(
            f"/v1/tasks/{rejected_id}",
            headers=AUTH,
        ).json()["plan"]
        rejection = {
            "plan_id": rejected_plan["id"],
            "plan_version": rejected_plan["version"],
            "reason": "scope rejected",
        }
        rejected = client.post(
            f"/v1/tasks/{rejected_id}/reject",
            headers=AUTH,
            json=rejection,
        )
        duplicate_rejection = client.post(
            f"/v1/tasks/{rejected_id}/reject",
            headers=AUTH,
            json=rejection,
        )
        assert duplicate_rejection.json() == rejected.json()
        assert rejected.json()["task"]["status"] == "REJECTED"
        assert rejected.json()["run_id"] is None
        rejected_detail = client.get(
            f"/v1/tasks/{rejected_id}",
            headers=AUTH,
        ).json()
        assert rejected_detail["plan"]["status"] == "REJECTED"
        assert rejected_detail["runs"] == []

        cancelled_task = _submit_planned(
            client,
            key="m4-1-cancel",
            objective="Modify a repository file then cancel",
        )
        cancelled_id = cancelled_task["task"]["id"]
        cancellation = {"reason": "operator cancelled"}
        cancelled = client.post(
            f"/v1/tasks/{cancelled_id}/cancel",
            headers=AUTH,
            json=cancellation,
        )
        duplicate_cancellation = client.post(
            f"/v1/tasks/{cancelled_id}/cancel",
            headers=AUTH,
            json=cancellation,
        )
        assert duplicate_cancellation.json() == cancelled.json()
        assert cancelled.json()["task"]["status"] == "CANCELLED"

        service = TaskService(postgres_repository)
        retry_task = service.submit("Retry failed work", idempotency_key="m4-1-retry")
        service.transition(
            retry_task.id,
            TaskStatus.FAILED,
            actor="test:executor",
            reason="seed a failed execution",
        )
        failed_run = postgres_repository.create_run(
            Run.queue(task_id=retry_task.id).with_status(RunStatus.FAILED)
        )
        retry_body = {"run_id": str(failed_run.id), "reason": "operator retry"}
        retried = client.post(
            f"/v1/tasks/{retry_task.id}/retry",
            headers=AUTH,
            json=retry_body,
        )
        duplicate_retry = client.post(
            f"/v1/tasks/{retry_task.id}/retry",
            headers=AUTH,
            json=retry_body,
        )
        assert duplicate_retry.json() == retried.json()
        assert retried.json()["task"]["status"] == "QUEUED"
        retry_detail = client.get(
            f"/v1/tasks/{retry_task.id}",
            headers=AUTH,
        ).json()
        assert len(retry_detail["runs"]) == 2
        assert retry_detail["runs"][1]["previous_run_id"] == str(failed_run.id)


def test_default_api_resumes_an_awaiting_plan_after_restart(
    database_url: str,
    postgres_schema: str,
    postgres_repository: PostgresTaskRepository,
) -> None:
    del postgres_repository
    settings = _settings(database_url, postgres_schema)
    first_app = create_app(settings=settings, readiness_probe=ReadyProbe())
    with TestClient(first_app) as first_client:
        submitted = _submit_planned(
            first_client,
            key="m4-1-restart",
            objective="Change the repository after restart",
        )
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
