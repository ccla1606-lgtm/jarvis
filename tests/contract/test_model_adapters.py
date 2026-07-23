from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from jarvis.models.adapters import DeepSeekAdapter, OpenAIResponsesAdapter
from jarvis.models.contracts import (
    FinishReason,
    MessageRole,
    ModelMessage,
    ModelProfile,
    ModelRequest,
    OutputSchema,
    StreamEventKind,
    ToolDefinition,
)
from jarvis.models.errors import ModelErrorCategory, ModelGatewayError
from jarvis.models.gateway import ModelGateway
from jarvis.models.policy import (
    DEEPSEEK_CAPABILITIES,
    OPENAI_CAPABILITIES,
    ModelCandidate,
    ModelCapabilities,
    ModelRouter,
)
from jarvis.models.ports import ProviderAdapter

ResponseFactory = Callable[[str, bool, bool], dict[str, Any]]

OUTPUT_SCHEMA = OutputSchema(
    "answer",
    {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    },
)

TOOL = ToolDefinition(
    "lookup",
    "Look up one value",
    {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
        "additionalProperties": False,
    },
)

REQUEST = ModelRequest(
    ModelProfile.FAST,
    (ModelMessage(MessageRole.USER, "hello"),),
)


def _openai_response(
    content: str,
    structured: bool,
    with_tool: bool,
) -> dict[str, Any]:
    del structured
    output: list[dict[str, Any]] = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": content}],
        }
    ]
    if with_tool:
        output.append(
            {
                "type": "function_call",
                "call_id": "call-openai",
                "name": "lookup",
                "arguments": '{"key":"value"}',
            }
        )
    return {
        "id": "response-openai",
        "status": "completed",
        "output": output,
        "usage": {
            "input_tokens": 5,
            "output_tokens": 3,
            "total_tokens": 8,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }


def _deepseek_response(
    content: str,
    structured: bool,
    with_tool: bool,
) -> dict[str, Any]:
    del structured
    message: dict[str, Any] = {"role": "assistant", "content": content}
    finish_reason = "stop"
    if with_tool:
        message["tool_calls"] = [
            {
                "id": "call-deepseek",
                "type": "function",
                "function": {
                    "name": "lookup",
                    "arguments": '{"key":"value"}',
                },
            }
        ]
        finish_reason = "tool_calls"
    return {
        "id": "response-deepseek",
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 3,
            "total_tokens": 8,
            "prompt_tokens_details": {"cached_tokens": 1},
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    }


PROVIDER_CASES: tuple[
    tuple[str, str, str, ModelCapabilities, ResponseFactory],
    ...,
] = (
    (
        "openai",
        "test-openai-model",
        "/v1/responses",
        OPENAI_CAPABILITIES,
        _openai_response,
    ),
    (
        "deepseek",
        "test-deepseek-model",
        "/chat/completions",
        DEEPSEEK_CAPABILITIES,
        _deepseek_response,
    ),
)


def _router(candidate: ModelCandidate) -> ModelRouter:
    return ModelRouter(
        {
            profile: (
                ModelCandidate(
                    profile,
                    candidate.provider,
                    candidate.model,
                    candidate.capabilities,
                ),
            )
            for profile in ModelProfile
        }
    )


def _adapter(
    provider: str,
    client: httpx.AsyncClient,
    capabilities: ModelCapabilities,
) -> ProviderAdapter:
    if provider == "openai":
        return OpenAIResponsesAdapter(
            "secret-openai",
            base_url="https://models.test/v1",
            capabilities=capabilities,
            client=client,
        )
    return DeepSeekAdapter(
        "secret-deepseek",
        base_url="https://models.test",
        capabilities=capabilities,
        client=client,
    )


@pytest.mark.parametrize(
    ("provider", "model", "expected_path", "capabilities", "response_factory"),
    PROVIDER_CASES,
)
def test_every_adapter_passes_normalized_contract(
    provider: str,
    model: str,
    expected_path: str,
    capabilities: ModelCapabilities,
    response_factory: ResponseFactory,
) -> None:
    captured: list[httpx.Request] = []

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=response_factory("hello", False, False))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = _adapter(provider, client, capabilities)
            candidate = ModelCandidate(ModelProfile.FAST, provider, model, capabilities)
            gateway = ModelGateway(
                router=_router(candidate),
                adapters={provider: adapter},
                max_retries_per_candidate=0,
            )
            response = await gateway.invoke(
                ModelRequest(
                    ModelProfile.FAST,
                    (ModelMessage(MessageRole.USER, "hello"),),
                )
            )

        assert response.content == "hello"
        assert response.structured_data is None
        assert response.tool_calls == ()
        assert response.usage.input_tokens == 5
        assert response.usage.output_tokens == 3
        assert response.usage.cached_input_tokens == 1
        assert response.usage.reasoning_tokens == 2
        assert response.resolution.provider == provider
        assert response.resolution.model == model
        assert response.finish_reason is FinishReason.STOP
        assert response.provider_request_id == f"response-{provider}"

    asyncio.run(scenario())

    assert captured[0].url.path == expected_path
    assert captured[0].headers["authorization"].startswith("Bearer ")
    assert model in captured[0].content.decode()


@pytest.mark.parametrize(
    ("provider", "model", "_expected_path", "capabilities", "response_factory"),
    PROVIDER_CASES,
)
def test_every_adapter_supports_validated_structured_output(
    provider: str,
    model: str,
    _expected_path: str,
    capabilities: ModelCapabilities,
    response_factory: ResponseFactory,
) -> None:
    captured_payloads: list[dict[str, Any]] = []

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            captured_payloads.append(__import__("json").loads(request.content))
            return httpx.Response(
                200,
                json=response_factory('{"answer":"yes"}', True, False),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = _adapter(provider, client, capabilities)
            candidate = ModelCandidate(ModelProfile.PLANNER, provider, model, capabilities)
            response = await ModelGateway(
                router=_router(candidate),
                adapters={provider: adapter},
                max_retries_per_candidate=0,
            ).invoke(
                ModelRequest(
                    ModelProfile.PLANNER,
                    (ModelMessage(MessageRole.USER, "answer as JSON"),),
                    output_schema=OUTPUT_SCHEMA,
                )
            )
        assert response.structured_data == {"answer": "yes"}

    asyncio.run(scenario())

    payload = captured_payloads[0]
    if provider == "openai":
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
    else:
        assert payload["response_format"] == {"type": "json_object"}
        assert "JSON Schema" in payload["messages"][0]["content"]


@pytest.mark.parametrize(
    ("provider", "model", "_expected_path", "capabilities", "response_factory"),
    PROVIDER_CASES,
)
def test_every_adapter_normalizes_tool_calls(
    provider: str,
    model: str,
    _expected_path: str,
    capabilities: ModelCapabilities,
    response_factory: ResponseFactory,
) -> None:
    async def scenario() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response_factory("", False, True))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = _adapter(provider, client, capabilities)
            candidate = ModelCandidate(ModelProfile.CODER, provider, model, capabilities)
            response = await ModelGateway(
                router=_router(candidate),
                adapters={provider: adapter},
                max_retries_per_candidate=0,
            ).invoke(
                ModelRequest(
                    ModelProfile.CODER,
                    (ModelMessage(MessageRole.USER, "use a tool"),),
                    tools=(TOOL,),
                )
            )
        assert response.tool_calls[0].name == "lookup"
        assert response.tool_calls[0].arguments == {"key": "value"}
        assert response.finish_reason is FinishReason.TOOL_CALLS

    asyncio.run(scenario())


class BlockingStream(httpx.AsyncByteStream):
    def __init__(self, first_event: bytes) -> None:
        self._first_event = first_event
        self.closed = False
        self.waiting = asyncio.Event()

    async def __aiter__(self) -> Any:
        yield self._first_event
        self.waiting.set()
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("provider", "model", "_expected_path", "capabilities", "_response_factory"),
    PROVIDER_CASES,
)
def test_every_adapter_releases_stream_on_cancellation(
    provider: str,
    model: str,
    _expected_path: str,
    capabilities: ModelCapabilities,
    _response_factory: ResponseFactory,
) -> None:
    if provider == "openai":
        event = b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
    else:
        event = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
    stream = BlockingStream(event)

    async def scenario() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=stream)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = _adapter(provider, client, capabilities)
            candidate = ModelCandidate(ModelProfile.FAST, provider, model, capabilities)
            gateway = ModelGateway(
                router=_router(candidate),
                adapters={provider: adapter},
                max_retries_per_candidate=0,
            )

            async def consume() -> None:
                async for event in gateway.stream(
                    ModelRequest(
                        ModelProfile.FAST,
                        (ModelMessage(MessageRole.USER, "stream"),),
                    )
                ):
                    assert event.kind is StreamEventKind.TEXT_DELTA

            task = asyncio.create_task(consume())
            await asyncio.wait_for(stream.waiting.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
    assert stream.closed


@pytest.mark.parametrize(
    ("provider", "model", "_expected_path", "capabilities", "_response_factory"),
    PROVIDER_CASES,
)
@pytest.mark.parametrize(
    ("status_code", "body", "category"),
    (
        (401, "credential-do-not-leak", ModelErrorCategory.AUTHENTICATION),
        (429, "rate limited", ModelErrorCategory.RATE_LIMIT),
        (500, "server failed", ModelErrorCategory.PROVIDER_UNAVAILABLE),
        (400, "maximum context length exceeded", ModelErrorCategory.CONTEXT_OVERFLOW),
    ),
)
def test_every_adapter_returns_sanitized_classified_http_errors(
    provider: str,
    model: str,
    _expected_path: str,
    capabilities: ModelCapabilities,
    _response_factory: ResponseFactory,
    status_code: int,
    body: str,
    category: ModelErrorCategory,
) -> None:
    async def scenario() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = _adapter(provider, client, capabilities)
            candidate = ModelCandidate(ModelProfile.FAST, provider, model, capabilities)
            gateway = ModelGateway(
                router=_router(candidate),
                adapters={provider: adapter},
                max_retries_per_candidate=0,
            )
            with pytest.raises(ModelGatewayError) as captured:
                await gateway.invoke(REQUEST)
            assert captured.value.category is category
            assert body not in str(captured.value)
            assert "credential-do-not-leak" not in str(captured.value)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("provider", "model", "_expected_path", "capabilities", "_response_factory"),
    PROVIDER_CASES,
)
def test_every_adapter_classifies_transport_timeout(
    provider: str,
    model: str,
    _expected_path: str,
    capabilities: ModelCapabilities,
    _response_factory: ResponseFactory,
) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("wire detail", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = _adapter(provider, client, capabilities)
            candidate = ModelCandidate(ModelProfile.FAST, provider, model, capabilities)
            with pytest.raises(ModelGatewayError) as captured:
                await ModelGateway(
                    router=_router(candidate),
                    adapters={provider: adapter},
                    max_retries_per_candidate=0,
                ).invoke(REQUEST)
            assert captured.value.category is ModelErrorCategory.TIMEOUT
            assert "wire detail" not in str(captured.value)

    asyncio.run(scenario())


def test_openai_tool_result_uses_responses_input_item() -> None:
    captured_payload: dict[str, Any] = {}

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json=_openai_response("done", False, False))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidate = ModelCandidate(
                ModelProfile.CODER,
                "openai",
                "test-openai-model",
                OPENAI_CAPABILITIES,
            )
            await ModelGateway(
                router=_router(candidate),
                adapters={
                    "openai": OpenAIResponsesAdapter(
                        "secret",
                        base_url="https://models.test/v1",
                        client=client,
                    )
                },
            ).invoke(
                ModelRequest(
                    ModelProfile.CODER,
                    (
                        ModelMessage(MessageRole.USER, "use tool"),
                        ModelMessage(
                            MessageRole.TOOL,
                            '{"value":"result"}',
                            tool_call_id="call-1",
                        ),
                    ),
                )
            )

    asyncio.run(scenario())
    assert captured_payload["input"][1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"value":"result"}',
    }


def test_deepseek_stream_reassembles_fragmented_tool_arguments() -> None:
    chunks = (
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"key":',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"arguments": '"value"}'},
                            }
                        ]
                    }
                }
            ]
        },
    )
    body = (
        "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
    ).encode()

    async def scenario() -> list[object]:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidate = ModelCandidate(
                ModelProfile.CODER,
                "deepseek",
                "test-deepseek-model",
                DEEPSEEK_CAPABILITIES,
            )
            gateway = ModelGateway(
                router=_router(candidate),
                adapters={
                    "deepseek": DeepSeekAdapter(
                        "secret",
                        base_url="https://models.test",
                        client=client,
                    )
                },
            )
            return [
                event
                async for event in gateway.stream(
                    ModelRequest(
                        ModelProfile.CODER,
                        (ModelMessage(MessageRole.USER, "use tool"),),
                        tools=(TOOL,),
                    )
                )
            ]

    events = asyncio.run(scenario())
    tool_events = [event for event in events if event.kind is StreamEventKind.TOOL_CALL]
    assert tool_events[0].tool_call is not None
    assert tool_events[0].tool_call.arguments == {"key": "value"}
