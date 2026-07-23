"""Stable error envelope, correlation ID, and development auth."""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import SecretStr
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from jarvis.api_contracts import ErrorDetail, ErrorResponse
from jarvis.domain.errors import (
    ApprovalMismatchError,
    ConcurrencyConflictError,
    DomainError,
    EntityNotFoundError,
    InvalidRetryError,
    InvalidTransitionError,
)

_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True, slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] | None = None


def install_api_boundary(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation = supplied if _CORRELATION_PATTERN.fullmatch(supplied) else str(uuid4())
        request.state.correlation_id = correlation
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
        return _error_response(
            request,
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            code="INVALID_PAYLOAD",
            message="Request validation failed",
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, error: DomainError) -> JSONResponse:
        status_code, code = _classify_domain_error(error)
        return _error_response(
            request,
            status_code=status_code,
            code=code,
            message=str(error),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _error: Exception) -> JSONResponse:
        return _error_response(
            request,
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="Unexpected server error",
        )


def require_api_token(supplied: str | None, expected: SecretStr) -> str:
    if supplied is None or not secrets.compare_digest(supplied, expected.get_secret_value()):
        raise ApiError(
            HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "A valid bearer token is required",
            {"WWW-Authenticate": "Bearer"},
        )
    return "api:development"


def invalid_cursor() -> ApiError:
    return ApiError(
        HTTP_400_BAD_REQUEST,
        "INVALID_CURSOR",
        "Last-Event-ID must be a non-negative task version",
    )


def _classify_domain_error(error: DomainError) -> tuple[int, str]:
    if isinstance(error, EntityNotFoundError):
        return HTTP_404_NOT_FOUND, "NOT_FOUND"
    if isinstance(error, ApprovalMismatchError):
        return HTTP_409_CONFLICT, "STALE_PLAN"
    if isinstance(error, ConcurrencyConflictError):
        return HTTP_409_CONFLICT, "VERSION_CONFLICT"
    if isinstance(error, InvalidTransitionError):
        return HTTP_409_CONFLICT, "INVALID_TRANSITION"
    if isinstance(error, InvalidRetryError):
        return HTTP_409_CONFLICT, "INVALID_RETRY"
    return HTTP_409_CONFLICT, "DOMAIN_CONFLICT"


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    correlation = getattr(request.state, "correlation_id", str(uuid4()))
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=correlation,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )
