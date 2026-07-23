"""FastAPI application factory and M0 endpoints."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from jarvis.config import Settings, get_settings
from jarvis.health import PostgresReadinessProbe, ReadinessProbe


class HealthResponse(BaseModel):
    """Stable health response."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "not_ready"]
    service: str
    detail: str | None = None


class DemoRequest(BaseModel):
    """Deterministic M0 request used to verify the assembled stack."""

    message: str = Field(min_length=1, max_length=2_000)


class DemoResponse(BaseModel):
    """M0 response proving API serialization and UI connectivity."""

    task_id: UUID
    status: Literal["accepted"]
    route: Literal["m0_scaffold"]
    message: str


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    """Build the API with injectable configuration and readiness dependencies."""

    resolved_settings = settings or get_settings()
    probe = readiness_probe or PostgresReadinessProbe(
        database_url=resolved_settings.database_url,
        connect_timeout_seconds=resolved_settings.database_connect_timeout_seconds,
    )

    app = FastAPI(
        title="Jarvis API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def liveness() -> HealthResponse:
        return HealthResponse(status="ok", service=resolved_settings.service_name)

    @app.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
        tags=["health"],
    )
    def readiness() -> HealthResponse | JSONResponse:
        result = probe.check()
        response = HealthResponse(
            status="ok" if result.ready else "not_ready",
            service=resolved_settings.service_name,
            detail=result.detail,
        )
        if not result.ready:
            return JSONResponse(status_code=503, content=response.model_dump(mode="json"))
        return response

    @app.post("/v1/demo", response_model=DemoResponse, status_code=202, tags=["demo"])
    def demo(request: DemoRequest) -> DemoResponse:
        return DemoResponse(
            task_id=uuid4(),
            status="accepted",
            route="m0_scaffold",
            message=request.message,
        )

    return app


app = create_app()
