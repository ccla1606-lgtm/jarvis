"""Bounded routing, retry, repair, fallback, and streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from jarvis.models.contracts import (
    FinishReason,
    ModelRequest,
    ModelResponse,
    Resolution,
    StreamEvent,
    StreamEventKind,
)
from jarvis.models.errors import ModelErrorCategory, ModelGatewayError
from jarvis.models.policy import ModelCandidate, ModelRouter
from jarvis.models.ports import ProviderAdapter, ProviderResult

FALLBACK_CATEGORIES = frozenset(
    {
        ModelErrorCategory.TIMEOUT,
        ModelErrorCategory.AUTHENTICATION,
        ModelErrorCategory.RATE_LIMIT,
        ModelErrorCategory.PROVIDER_UNAVAILABLE,
        ModelErrorCategory.CONTEXT_OVERFLOW,
        ModelErrorCategory.INVALID_RESPONSE,
    }
)


class ModelGateway:
    """Provider-independent implementation of ModelPort."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        adapters: Mapping[str, ProviderAdapter],
        max_retries_per_candidate: int = 1,
        max_structured_repairs: int = 1,
    ) -> None:
        if max_retries_per_candidate < 0 or max_structured_repairs < 0:
            raise ValueError("model retry and repair limits cannot be negative")
        self._router = router
        self._adapters = dict(adapters)
        self._max_retries = max_retries_per_candidate
        self._max_repairs = max_structured_repairs
        if not self._adapters:
            raise ValueError("at least one provider adapter is required")
        if any(key != adapter.provider for key, adapter in self._adapters.items()):
            raise ValueError("adapter mapping keys must match provider identifiers")

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        _validate_requested_schema(request)
        candidates = self._router.candidates(request)
        last_error: ModelGatewayError | None = None
        fallback_reason: str | None = None
        total_attempt = 0

        for candidate in candidates:
            adapter = self._adapter(candidate)
            current_request = request
            repairs = 0
            retries = 0
            while True:
                total_attempt += 1
                try:
                    provider_result = await adapter.invoke(current_request, candidate)
                except ModelGatewayError as error:
                    last_error = error
                    if error.retryable and retries < self._max_retries:
                        retries += 1
                        continue
                    if error.category not in FALLBACK_CATEGORIES:
                        raise
                    fallback_reason = error.category.value
                    break

                try:
                    structured = _validate_structured_output(
                        provider_result,
                        current_request,
                    )
                except ModelGatewayError as error:
                    last_error = error
                    if repairs < self._max_repairs:
                        repairs += 1
                        current_request = request.for_repair(
                            invalid_output=provider_result.content,
                            validation_error=str(error),
                        )
                        continue
                    fallback_reason = error.category.value
                    break

                return _response(
                    provider_result,
                    candidate,
                    attempt=total_attempt,
                    fallback_reason=fallback_reason,
                    structured_data=structured,
                )

        if last_error is not None:
            raise last_error
        raise ModelGatewayError(
            ModelErrorCategory.UNKNOWN,
            "model routing exhausted without a result",
            retryable=False,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        if request.output_schema is not None:
            raise ModelGatewayError(
                ModelErrorCategory.CAPABILITY_MISMATCH,
                "validated structured output is not available in streaming mode",
                retryable=False,
            )
        candidates = self._router.candidates(request, streaming=True)
        fallback_reason: str | None = None
        last_error: ModelGatewayError | None = None
        total_attempt = 0

        for candidate in candidates:
            adapter = self._adapter(candidate)
            retries = 0
            while True:
                total_attempt += 1
                emitted_output = False
                resolution = Resolution(
                    request.profile,
                    candidate.provider,
                    candidate.model,
                    candidate.account,
                    total_attempt,
                    fallback_reason,
                )
                try:
                    async for event in adapter.stream(request, candidate):
                        normalized = _stream_event(event, resolution)
                        if normalized.kind in {
                            StreamEventKind.TEXT_DELTA,
                            StreamEventKind.TOOL_CALL,
                        }:
                            emitted_output = True
                        yield normalized
                    return
                except ModelGatewayError as error:
                    if emitted_output:
                        raise ModelGatewayError(
                            ModelErrorCategory.PARTIAL_OUTPUT,
                            "model stream failed after output was emitted",
                            provider=candidate.provider,
                            retryable=False,
                        ) from error
                    last_error = error
                    if error.retryable and retries < self._max_retries:
                        retries += 1
                        continue
                    if error.category not in FALLBACK_CATEGORIES:
                        raise
                    fallback_reason = error.category.value
                    break

        if last_error is not None:
            raise last_error
        raise ModelGatewayError(
            ModelErrorCategory.UNKNOWN,
            "model stream routing exhausted without a result",
            retryable=False,
        )

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            await adapter.aclose()

    def _adapter(self, candidate: ModelCandidate) -> ProviderAdapter:
        try:
            return self._adapters[candidate.provider]
        except KeyError as error:
            raise ModelGatewayError(
                ModelErrorCategory.CAPABILITY_MISMATCH,
                f"provider {candidate.provider} is not configured",
                provider=candidate.provider,
                retryable=False,
            ) from error


def _validate_structured_output(
    result: ProviderResult,
    request: ModelRequest,
) -> dict[str, Any] | None:
    output_schema = request.output_schema
    if output_schema is None:
        return None
    try:
        Draft202012Validator.check_schema(output_schema.schema)
        decoded = json.loads(result.content)
        if not isinstance(decoded, dict):
            raise ValidationError("root value is not an object")
        Draft202012Validator(output_schema.schema).validate(decoded)
    except (ValueError, SchemaError, ValidationError) as error:
        raise ModelGatewayError(
            ModelErrorCategory.INVALID_RESPONSE,
            "structured model output failed schema validation",
            retryable=False,
        ) from error
    return decoded


def _validate_requested_schema(request: ModelRequest) -> None:
    if request.output_schema is None:
        return
    try:
        Draft202012Validator.check_schema(request.output_schema.schema)
    except SchemaError as error:
        raise ModelGatewayError(
            ModelErrorCategory.INVALID_REQUEST,
            "requested output schema is invalid",
            retryable=False,
        ) from error


def _response(
    result: ProviderResult,
    candidate: ModelCandidate,
    *,
    attempt: int,
    fallback_reason: str | None,
    structured_data: dict[str, Any] | None,
) -> ModelResponse:
    try:
        finish_reason = FinishReason(result.finish_reason)
    except ValueError:
        finish_reason = FinishReason.OTHER
    return ModelResponse(
        content=result.content,
        structured_data=structured_data,
        tool_calls=result.tool_calls,
        usage=result.usage,
        resolution=Resolution(
            candidate.profile,
            candidate.provider,
            candidate.model,
            candidate.account,
            attempt,
            fallback_reason,
        ),
        finish_reason=finish_reason,
        provider_request_id=result.provider_request_id,
    )


def _stream_event(event: Any, resolution: Resolution) -> StreamEvent:
    try:
        kind = StreamEventKind(event.kind)
    except ValueError as error:
        raise ModelGatewayError(
            ModelErrorCategory.INVALID_RESPONSE,
            "provider emitted an unknown stream event",
            provider=resolution.provider,
            retryable=False,
        ) from error
    return StreamEvent(
        kind=kind,
        resolution=resolution,
        text=event.text,
        tool_call=event.tool_call,
        usage=event.usage,
    )
