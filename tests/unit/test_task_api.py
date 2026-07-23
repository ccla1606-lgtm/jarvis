from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.api_contracts import SubmitTaskResponse
from jarvis.application.task_service import TaskService
from jarvis.config import Settings
from jarvis.domain.entities import Plan, PlanStep, Run, RunStatus
from jarvis.domain.task import Task, TaskStatus
from jarvis.health import ReadinessResult
from jarvis.infrastructure.memory_repository import InMemoryTaskRepository

TOKEN = "unit-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@dataclass(frozen=True)
class ReadyProbe:
    def check(self) -> ReadinessResult:
        return ReadinessResult(ready=True, detail="ready")


def build_client(
    repository: InMemoryTaskRepository | None = None,
) -> tuple[TestClient, InMemoryTaskRepository]:
    resolved_repository = repository or InMemoryTaskRepository()
    settings = Settings(
        environment="test",
        service_name="test-api",
        database_url="postgresql://unused",
        api_token=TOKEN,
    )
    return (
        TestClient(
            create_app(
                settings=settings,
                readiness_probe=ReadyProbe(),
                repository=resolved_repository,
            )
        ),
        resolved_repository,
    )


def awaiting_plan(
    repository: InMemoryTaskRepository,
    *,
    key: str = "planned-task",
    version: int = 1,
) -> tuple[Task, Plan]:
    service = TaskService(repository)
    task = service.submit("Implement the approved change", idempotency_key=key)
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
        reason="complex task",
    )
    plan = service.propose_plan(
        task.id,
        version=version,
        steps=(
            PlanStep(
                1,
                "Implement",
                tools=("apply_patch",),
                repositories=("owner/repo",),
            ),
            PlanStep(
                2,
                "Verify",
                depends_on=(1,),
                tools=("pytest",),
                repositories=("owner/repo",),
            ),
        ),
    )
    task = service.transition(
        task.id,
        TaskStatus.AWAITING_APPROVAL,
        actor="brain",
        reason="plan ready",
    )
    return task, plan


def test_bearer_auth_and_correlation_error_contract_are_stable() -> None:
    client, _repository = build_client()

    response = client.get(
        "/v1/tasks",
        headers={"X-Correlation-ID": "contract-test-42"},
    )

    assert response.status_code == 401
    assert response.headers["X-Correlation-ID"] == "contract-test-42"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "A valid bearer token is required",
            "correlation_id": "contract-test-42",
        }
    }


def test_duplicate_submit_returns_one_canonical_task() -> None:
    client, repository = build_client()
    request = {
        "objective": "Create one durable task",
        "allowed_tools": [" git ", "pytest"],
        "allowed_repositories": ["owner/repo"],
        "side_effects_allowed": False,
    }

    first = client.post(
        "/v1/tasks",
        headers={**AUTH, "Idempotency-Key": "same-command"},
        json=request,
    )
    second = client.post(
        "/v1/tasks",
        headers={**AUTH, "Idempotency-Key": "same-command"},
        json=request,
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["task"]["id"] == second.json()["task"]["id"]
    assert first.json()["orchestration"] == {"route": None, "interrupted": False}
    assert len(repository.list_tasks()) == 1


def test_invalid_scope_payload_has_stable_error_code() -> None:
    client, _repository = build_client()

    response = client.post(
        "/v1/tasks",
        headers={**AUTH, "Idempotency-Key": "bad-scope"},
        json={
            "objective": "Invalid scope",
            "allowed_tools": ["pytest", " pytest "],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PAYLOAD"


def test_approval_is_bound_to_exact_plan_and_creates_one_run() -> None:
    client, repository = build_client()
    task, plan = awaiting_plan(repository)

    response = client.post(
        f"/v1/tasks/{task.id}/approve",
        headers=AUTH,
        json={
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "reason": "scope accepted",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "QUEUED"
    assert payload["approval_id"]
    assert payload["run_id"]
    runs = repository.list_runs(task.id)
    assert len(runs) == 1
    assert runs[0].plan_id == plan.id
    assert runs[0].plan_version == plan.version


def test_stale_approval_creates_no_run_and_preserves_waiting_state() -> None:
    client, repository = build_client()
    task, plan = awaiting_plan(repository, version=2)

    response = client.post(
        f"/v1/tasks/{task.id}/approve",
        headers=AUTH,
        json={
            "plan_id": str(plan.id),
            "plan_version": 1,
            "reason": "stale browser tab",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_PLAN"
    assert repository.get_task(task.id).status is TaskStatus.AWAITING_APPROVAL
    assert repository.list_runs(task.id) == ()


def test_rejection_creates_no_run() -> None:
    client, repository = build_client()
    task, plan = awaiting_plan(repository)

    response = client.post(
        f"/v1/tasks/{task.id}/reject",
        headers=AUTH,
        json={
            "plan_id": str(plan.id),
            "plan_version": plan.version,
            "reason": "scope is too broad",
        },
    )

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "REJECTED"
    assert response.json()["run_id"] is None
    assert repository.list_runs(task.id) == ()


def test_cancel_is_idempotent() -> None:
    client, repository = build_client()
    task = TaskService(repository).submit("Cancel me", idempotency_key="cancel")

    first = client.post(
        f"/v1/tasks/{task.id}/cancel",
        headers=AUTH,
        json={"reason": "operator cancelled"},
    )
    second = client.post(
        f"/v1/tasks/{task.id}/cancel",
        headers=AUTH,
        json={"reason": "duplicate command"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["task"]["version"] == second.json()["task"]["version"] == 1
    assert len(repository.list_transitions(task.id)) == 1


def test_retry_preserves_failed_attempt_and_links_new_attempt() -> None:
    client, repository = build_client()
    service = TaskService(repository)
    task = service.submit("Retry me", idempotency_key="retry")
    service.transition(
        task.id,
        TaskStatus.FAILED,
        actor="runner",
        reason="first attempt failed",
    )
    failed = repository.create_run(Run.queue(task_id=task.id).with_status(RunStatus.FAILED))

    response = client.post(
        f"/v1/tasks/{task.id}/retry",
        headers=AUTH,
        json={"run_id": str(failed.id), "reason": "retry approved"},
    )

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "QUEUED"
    runs = repository.list_runs(task.id)
    assert len(runs) == 2
    assert runs[0] == failed
    assert runs[1].attempt == 2
    assert runs[1].previous_run_id == failed.id
    assert str(runs[1].id) == response.json()["run_id"]


def test_invalid_retry_does_not_move_task_or_create_attempt() -> None:
    client, repository = build_client()
    service = TaskService(repository)
    task = service.submit("Do not retry", idempotency_key="invalid-retry")
    failed_task = service.transition(
        task.id,
        TaskStatus.FAILED,
        actor="runner",
        reason="task failed before run status update",
    )
    active = repository.create_run(Run.queue(task_id=task.id))

    response = client.post(
        f"/v1/tasks/{task.id}/retry",
        headers=AUTH,
        json={"run_id": str(active.id), "reason": "invalid retry"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_RETRY"
    assert repository.get_task(task.id) == failed_task
    assert repository.list_runs(task.id) == (active,)


def test_invalid_transition_is_classified_without_partial_approval() -> None:
    client, repository = build_client()
    service = TaskService(repository)
    task = service.submit("Not ready", idempotency_key="not-ready")
    plan = service.propose_plan(
        task.id,
        version=1,
        steps=(PlanStep(1, "Premature plan"),),
    )

    response = client.post(
        f"/v1/tasks/{task.id}/approve",
        headers=AUTH,
        json={
            "plan_id": str(plan.id),
            "plan_version": 1,
            "reason": "too early",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert repository.get_plan(plan.id).status.value == "PROPOSED"
    assert repository.list_runs(task.id) == ()


def test_task_detail_returns_latest_plan_and_list_projection() -> None:
    client, repository = build_client()
    service = TaskService(repository)
    task = service.submit("Versioned plan", idempotency_key="versions")
    service.propose_plan(task.id, version=1, steps=(PlanStep(1, "Old"),))
    latest = service.propose_plan(task.id, version=2, steps=(PlanStep(1, "New"),))

    detail = client.get(f"/v1/tasks/{task.id}", headers=AUTH)
    listed = client.get("/v1/tasks?limit=1", headers=AUTH)

    assert detail.status_code == 200
    assert detail.json()["plan"]["id"] == str(latest.id)
    assert detail.json()["plan"]["version"] == 2
    assert listed.status_code == 200
    assert listed.json()["tasks"][0]["id"] == str(task.id)


def test_sse_reconnect_uses_task_version_without_duplicate_transitions() -> None:
    client, repository = build_client()
    service = TaskService(repository)
    task = service.submit("Stream me", idempotency_key="events")
    service.transition(task.id, TaskStatus.TRIAGING, actor="brain", reason="triage")
    service.transition(task.id, TaskStatus.QUEUED, actor="brain", reason="fast task")

    initial = client.get(f"/v1/tasks/{task.id}/events", headers=AUTH)
    resumed = client.get(
        f"/v1/tasks/{task.id}/events",
        headers={**AUTH, "Last-Event-ID": "1"},
    )
    current = client.get(
        f"/v1/tasks/{task.id}/events",
        headers={**AUTH, "Last-Event-ID": "2"},
    )

    assert initial.status_code == 200
    assert initial.text.count("event: task.transition") == 2
    assert "id: 1\n" in initial.text
    assert "id: 2\n" in initial.text
    assert resumed.text.count("event: task.transition") == 1
    assert "id: 1\n" not in resumed.text
    assert "id: 2\n" in resumed.text
    assert current.text == ": up-to-date\n\n"


def test_bad_sse_cursor_and_missing_task_use_stable_codes() -> None:
    client, _repository = build_client()

    bad_cursor = client.get(
        f"/v1/tasks/{uuid4()}/events",
        headers={**AUTH, "Last-Event-ID": "not-a-version"},
    )
    missing = client.get(f"/v1/tasks/{uuid4()}", headers=AUTH)

    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"]["code"] == "INVALID_CURSOR"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_openapi_declares_versioned_contracts_and_bearer_auth() -> None:
    client, _repository = build_client()

    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "Jarvis API"
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    submit = schema["paths"]["/v1/tasks"]["post"]
    assert submit["security"] == [{"HTTPBearer": []}]
    assert submit["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SubmitTaskResponse"
    }


def test_openapi_response_model_accepts_fixture_used_by_web_client() -> None:
    fixture_path = Path("apps/web/src/fixtures/submit-task-response.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    client, _repository = build_client()
    schema = client.get("/openapi.json").json()

    parsed = SubmitTaskResponse.model_validate(fixture)

    assert parsed.model_dump(mode="json") == fixture
    assert schema["paths"]["/v1/tasks"]["post"]["responses"]["202"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/SubmitTaskResponse")
