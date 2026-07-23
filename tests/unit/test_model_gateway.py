from __future__ import annotations

import asyncio

import pytest

from jarvis.models.contracts import (
    MessageRole,
    ModelMessage,
    ModelProfile,
    ModelRequest,
    ModelUsage,
    OutputSchema,
    StreamEventKind,
)
from jarvis.models.errors import ModelErrorCategory, ModelGatewayError
from jarvis.models.fake import FakeProviderAdapter
from jarvis.models.gateway import ModelGateway
from jarvis.models.policy import (
    ModelCandidate,
    ModelCapabilities,
    ModelRouter,
    StructuredOutputMode,
)
from jarvis.models.ports import ProviderResult, ProviderStreamEvent

CAPABILITIES = ModelCapabilities(
    StructuredOutputMode.JSON_SCHEMA,
    tool_calls=True,
    streaming=True,
    cancellation=True,
    reasoning_controls=True,
    context_window_tokens=100_000,
    max_output_tokens=10_000,
)

SCHEMA = OutputSchema(
    "result",
    {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
        "additionalProperties": False,
    },
)

REQUEST = ModelRequest(
    ModelProfile.FAST,
    (ModelMessage(MessageRole.USER, "hello"),),
)


def _result(content: str = "ok") -> ProviderResult:
    return ProviderResult(
        content=content,
        tool_calls=(),
        usage=ModelUsage(2, 1, 3),
        finish_reason="stop",
        provider_request_id="provider-request",
    )


def _router(*candidates: ModelCandidate) -> ModelRouter:
    return ModelRouter({profile: candidates for profile in ModelProfile})


def _candidate(provider: str) -> ModelCandidate:
    return ModelCandidate(
        ModelProfile.FAST,
        provider,
        f"{provider}-model",
        CAPABILITIES,
    )


def _error(category: ModelErrorCategory) -> ModelGatewayError:
    return ModelGatewayError(category, f"safe {category.value}", provider="primary")


def test_invalid_structured_output_receives_one_bounded_repair() -> None:
    adapter = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(_result('{"wrong":1}'), _result('{"value":2}')),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary")),
        adapters={"primary": adapter},
        max_structured_repairs=1,
    )

    response = asyncio.run(
        gateway.invoke(
            ModelRequest(
                ModelProfile.FAST,
                REQUEST.messages,
                output_schema=SCHEMA,
            )
        )
    )

    assert response.structured_data == {"value": 2}
    assert len(adapter.calls) == 2
    assert "previous result was invalid" in adapter.calls[1][0].messages[-1].content


def test_structured_repair_limit_is_enforced() -> None:
    adapter = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(_result("not-json"), _result('{"wrong":1}')),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary")),
        adapters={"primary": adapter},
        max_structured_repairs=1,
    )

    with pytest.raises(ModelGatewayError) as captured:
        asyncio.run(
            gateway.invoke(
                ModelRequest(
                    ModelProfile.FAST,
                    REQUEST.messages,
                    output_schema=SCHEMA,
                )
            )
        )

    assert captured.value.category is ModelErrorCategory.INVALID_RESPONSE
    assert len(adapter.calls) == 2


def test_retryable_error_retries_then_falls_back_with_resolution_reason() -> None:
    primary = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(
            _error(ModelErrorCategory.TIMEOUT),
            _error(ModelErrorCategory.TIMEOUT),
        ),
    )
    fallback = FakeProviderAdapter(
        "fallback",
        capabilities=CAPABILITIES,
        results=(_result("fallback answer"),),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary"), _candidate("fallback")),
        adapters={"primary": primary, "fallback": fallback},
        max_retries_per_candidate=1,
    )

    response = asyncio.run(gateway.invoke(REQUEST))

    assert len(primary.calls) == 2
    assert len(fallback.calls) == 1
    assert response.content == "fallback answer"
    assert response.resolution.provider == "fallback"
    assert response.resolution.attempt == 3
    assert response.resolution.fallback_reason == "timeout"


@pytest.mark.parametrize(
    "category",
    (
        ModelErrorCategory.TIMEOUT,
        ModelErrorCategory.RATE_LIMIT,
        ModelErrorCategory.PROVIDER_UNAVAILABLE,
    ),
)
def test_only_retryable_categories_retry(category: ModelErrorCategory) -> None:
    adapter = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(_error(category), _result()),
    )
    response = asyncio.run(
        ModelGateway(
            router=_router(_candidate("primary")),
            adapters={"primary": adapter},
            max_retries_per_candidate=1,
        ).invoke(REQUEST)
    )
    assert response.content == "ok"
    assert len(adapter.calls) == 2


def test_invalid_request_does_not_retry_or_fall_back() -> None:
    primary = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(_error(ModelErrorCategory.INVALID_REQUEST),),
    )
    fallback = FakeProviderAdapter(
        "fallback",
        capabilities=CAPABILITIES,
        results=(_result("must not run"),),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary"), _candidate("fallback")),
        adapters={"primary": primary, "fallback": fallback},
        max_retries_per_candidate=5,
    )

    with pytest.raises(ModelGatewayError) as captured:
        asyncio.run(gateway.invoke(REQUEST))

    assert captured.value.category is ModelErrorCategory.INVALID_REQUEST
    assert len(primary.calls) == 1
    assert not fallback.calls


def test_authentication_failure_falls_back_without_retry() -> None:
    primary = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(_error(ModelErrorCategory.AUTHENTICATION),),
    )
    fallback = FakeProviderAdapter(
        "fallback",
        capabilities=CAPABILITIES,
        results=(_result(),),
    )

    response = asyncio.run(
        ModelGateway(
            router=_router(_candidate("primary"), _candidate("fallback")),
            adapters={"primary": primary, "fallback": fallback},
            max_retries_per_candidate=3,
        ).invoke(REQUEST)
    )

    assert len(primary.calls) == 1
    assert response.resolution.fallback_reason == "authentication"


def test_partial_stream_failure_never_falls_back() -> None:
    primary = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        stream_events=(
            ProviderStreamEvent(kind="text_delta", text="partial"),
            _error(ModelErrorCategory.TIMEOUT),
        ),
    )
    fallback = FakeProviderAdapter(
        "fallback",
        capabilities=CAPABILITIES,
        stream_events=(ProviderStreamEvent(kind="done"),),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary"), _candidate("fallback")),
        adapters={"primary": primary, "fallback": fallback},
    )

    async def consume() -> None:
        with pytest.raises(ModelGatewayError) as captured:
            async for event in gateway.stream(REQUEST):
                assert event.kind is StreamEventKind.TEXT_DELTA
        assert captured.value.category is ModelErrorCategory.PARTIAL_OUTPUT

    asyncio.run(consume())
    assert not fallback.calls


def test_stream_can_fall_back_before_output() -> None:
    primary = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        stream_events=(_error(ModelErrorCategory.PROVIDER_UNAVAILABLE),),
    )
    fallback = FakeProviderAdapter(
        "fallback",
        capabilities=CAPABILITIES,
        stream_events=(
            ProviderStreamEvent(kind="text_delta", text="answer"),
            ProviderStreamEvent(kind="done"),
        ),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary"), _candidate("fallback")),
        adapters={"primary": primary, "fallback": fallback},
        max_retries_per_candidate=0,
    )

    async def consume() -> list[object]:
        return [event async for event in gateway.stream(REQUEST)]

    events = asyncio.run(consume())
    assert events[0].kind is StreamEventKind.TEXT_DELTA
    assert events[0].resolution.provider == "fallback"
    assert events[0].resolution.fallback_reason == "provider_unavailable"
    assert events[-1].kind is StreamEventKind.DONE


def test_structured_output_is_explicitly_rejected_for_streaming() -> None:
    adapter = FakeProviderAdapter("primary", capabilities=CAPABILITIES)
    gateway = ModelGateway(
        router=_router(_candidate("primary")),
        adapters={"primary": adapter},
    )

    async def consume() -> None:
        with pytest.raises(ModelGatewayError) as captured:
            async for _event in gateway.stream(
                ModelRequest(
                    ModelProfile.FAST,
                    REQUEST.messages,
                    output_schema=SCHEMA,
                )
            ):
                raise AssertionError("structured streaming must fail before an event")
        assert captured.value.category is ModelErrorCategory.CAPABILITY_MISMATCH

    asyncio.run(consume())


def test_invalid_requested_schema_fails_before_provider_call() -> None:
    adapter = FakeProviderAdapter(
        "primary",
        capabilities=CAPABILITIES,
        results=(_result('{"value":1}'),),
    )
    gateway = ModelGateway(
        router=_router(_candidate("primary")),
        adapters={"primary": adapter},
    )
    invalid_schema = OutputSchema(
        "invalid",
        {
            "type": "object",
            "properties": {"value": {"type": "not-a-json-schema-type"}},
        },
    )

    with pytest.raises(ModelGatewayError) as captured:
        asyncio.run(
            gateway.invoke(
                ModelRequest(
                    ModelProfile.FAST,
                    REQUEST.messages,
                    output_schema=invalid_schema,
                )
            )
        )

    assert captured.value.category is ModelErrorCategory.INVALID_REQUEST
    assert not adapter.calls
