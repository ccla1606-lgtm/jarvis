"""FastAPI application factory and versioned endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from jarvis.api_contracts import DemoRequest, DemoResponse, HealthResponse
from jarvis.api_errors import install_api_boundary
from jarvis.api_routes import create_task_router
from jarvis.config import Settings, get_settings
from jarvis.health import PostgresReadinessProbe, ReadinessProbe
from jarvis.infrastructure.brain_runtime import BrainRuntimeHandle, postgres_brain_runtime
from jarvis.infrastructure.model_gateway import build_model_gateway
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository
from jarvis.ports.brain_runtime import BrainRuntimePort
from jarvis.ports.task_repository import TaskRepository


def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    repository: TaskRepository | None = None,
    brain_runtime: BrainRuntimePort | None = None,
) -> FastAPI:
    """Build the API and compose the default PostgreSQL-backed brain runtime."""

    resolved_settings = settings or get_settings()
    probe = readiness_probe or PostgresReadinessProbe(
        database_url=resolved_settings.database_url,
        connect_timeout_seconds=resolved_settings.database_connect_timeout_seconds,
    )
    task_repository = repository or PostgresTaskRepository(
        resolved_settings.database_url,
        schema=resolved_settings.database_schema,
    )

    default_runtime = brain_runtime is None and repository is None
    runtime_handle = BrainRuntimeHandle() if default_runtime else None
    model_gateway = build_model_gateway(resolved_settings) if default_runtime else None
    routed_runtime: BrainRuntimePort | None = runtime_handle or brain_runtime

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if runtime_handle is None or model_gateway is None:
            yield
            return
        try:
            async with postgres_brain_runtime(
                database_url=resolved_settings.database_url,
                schema=resolved_settings.database_schema,
                repository=task_repository,
                models=model_gateway,
            ) as runtime:
                runtime_handle.bind(runtime)
                yield
        finally:
            runtime_handle.clear()
            await model_gateway.aclose()

    app = FastAPI(
        title="Jarvis API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    install_api_boundary(app)

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

    app.include_router(
        create_task_router(
            repository=task_repository,
            api_token=resolved_settings.api_token,
            brain_runtime=routed_runtime,
        )
    )

    return app


app = create_app()
