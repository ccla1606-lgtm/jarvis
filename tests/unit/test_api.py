from dataclasses import dataclass

from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.config import Settings
from jarvis.health import ReadinessResult


@dataclass(frozen=True)
class StubReadinessProbe:
    result: ReadinessResult

    def check(self) -> ReadinessResult:
        return self.result


def build_client(result: ReadinessResult) -> TestClient:
    settings = Settings(
        environment="test",
        service_name="test-api",
        database_url="postgresql://unused",
    )
    return TestClient(
        create_app(
            settings=settings,
            readiness_probe=StubReadinessProbe(result),
        )
    )


def test_liveness_does_not_depend_on_postgres() -> None:
    client = build_client(ReadinessResult(ready=False, detail="offline"))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "test-api",
        "detail": None,
    }


def test_readiness_is_ok_when_dependency_is_ready() -> None:
    client = build_client(ReadinessResult(ready=True, detail="postgres ready"))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "test-api",
        "detail": "postgres ready",
    }


def test_readiness_is_503_when_dependency_is_unavailable() -> None:
    client = build_client(ReadinessResult(ready=False, detail="postgres unavailable"))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "test-api",
        "detail": "postgres unavailable",
    }


def test_demo_endpoint_validates_and_returns_contract() -> None:
    client = build_client(ReadinessResult(ready=True, detail="ready"))

    response = client.post("/v1/demo", json={"message": "Jarvis online"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["route"] == "m0_scaffold"
    assert payload["message"] == "Jarvis online"
    assert payload["task_id"]


def test_demo_endpoint_rejects_empty_message() -> None:
    client = build_client(ReadinessResult(ready=True, detail="ready"))

    response = client.post("/v1/demo", json={"message": ""})

    assert response.status_code == 422
