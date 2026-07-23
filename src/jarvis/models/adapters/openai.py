"""OpenAI Responses API adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import SecretStr

from jarvis.models.adapters.http import (
    HttpModelAdapter,
    invalid_provider_response,
    stream_done,
)
from jarvis.models.contracts import (
    ModelMessage,
    ModelRequest,
    ModelUsage,
    ToolCall,
)
from jarvis.models.policy import OPENAI_CAPABILITIES, ModelCandidate, ModelCapabilities
from jarvis.models.ports import ProviderResult, ProviderStreamEvent


class OpenAIResponsesAdapter(HttpModelAdapter):
    """Translate normalized contracts to and from OpenAI Responses API."""

    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        base_url: str = "https://api.openai.com/v1",
        capabilities: ModelCapabilities = OPENAI_CAPABILITIES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            provider="openai",
            api_key=api_key,
            base_url=base_url,
            capabilities=capabilities,
            client=client,
        )

    async def invoke(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> ProviderResult:
        _require_candidate(candidate, self.provider)
        payload = _request_payload(request, candidate.model, stream=False)
        data = await self._post_json(
            "/responses",
            payload=payload,
            timeout=request.timeout_seconds,
        )
        return _parse_response(data, self.provider)

    async def stream(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> AsyncIterator[ProviderStreamEvent]:
        _require_candidate(candidate, self.provider)
        payload = _request_payload(request, candidate.model, stream=True)
        async for event in self._stream_sse(
            "/responses",
            payload=payload,
            timeout=request.timeout_seconds,
        ):
            event_type = event.get("type")
            if event_type == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    yield ProviderStreamEvent(kind="text_delta", text=delta)
            elif event_type == "response.output_item.done":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "function_call":
                    yield ProviderStreamEvent(
                        kind="tool_call",
                        tool_call=_parse_tool_call(item, self.provider),
                    )
            elif event_type == "response.completed":
                response = event.get("response")
                if isinstance(response, dict):
                    usage = _parse_usage(response.get("usage"), self.provider)
                    yield ProviderStreamEvent(kind="usage", usage=usage)
        yield stream_done()


def _request_payload(
    request: ModelRequest,
    model: str,
    *,
    stream: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": [_input_item(message) for message in request.messages],
        "max_output_tokens": request.max_output_tokens,
        "stream": stream,
    }
    if request.output_schema is not None:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": request.output_schema.name,
                "schema": request.output_schema.schema,
                "strict": True,
            }
        }
    if request.tools:
        payload["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": True,
            }
            for tool in request.tools
        ]
    return payload


def _input_item(message: ModelMessage) -> dict[str, Any]:
    if message.tool_call_id is not None:
        return {
            "type": "function_call_output",
            "call_id": message.tool_call_id,
            "output": message.content,
        }
    return {"role": message.role.value, "content": message.content}


def _parse_response(data: dict[str, Any], provider: str) -> ProviderResult:
    output = data.get("output")
    if not isinstance(output, list):
        raise invalid_provider_response(provider, "missing output list")
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call":
            tool_calls.append(_parse_tool_call(item, provider))
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and isinstance(
                part.get("text"),
                str,
            ):
                text_parts.append(part["text"])

    status = data.get("status")
    incomplete = data.get("incomplete_details")
    reason = "stop"
    if status == "incomplete" and isinstance(incomplete, dict):
        reason = "length" if incomplete.get("reason") == "max_output_tokens" else "other"
    elif tool_calls:
        reason = "tool_calls"

    return ProviderResult(
        content="".join(text_parts),
        tool_calls=tuple(tool_calls),
        usage=_parse_usage(data.get("usage"), provider),
        finish_reason=reason,
        provider_request_id=data.get("id") if isinstance(data.get("id"), str) else None,
    )


def _parse_tool_call(item: dict[str, Any], provider: str) -> ToolCall:
    identifier = item.get("call_id") or item.get("id")
    name = item.get("name")
    arguments = item.get("arguments", "{}")
    if not isinstance(identifier, str) or not isinstance(name, str):
        raise invalid_provider_response(provider, "invalid tool call identity")
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
    except ValueError as error:
        raise invalid_provider_response(provider, "invalid tool call arguments") from error
    if not isinstance(parsed, dict):
        raise invalid_provider_response(provider, "tool arguments must be an object")
    return ToolCall(identifier, name, parsed)


def _parse_usage(value: Any, provider: str) -> ModelUsage:
    if not isinstance(value, dict):
        raise invalid_provider_response(provider, "missing usage")
    input_tokens = _nonnegative_int(value.get("input_tokens"), provider, "input_tokens")
    output_tokens = _nonnegative_int(value.get("output_tokens"), provider, "output_tokens")
    total = value.get("total_tokens", input_tokens + output_tokens)
    total_tokens = _nonnegative_int(total, provider, "total_tokens")
    input_details = value.get("input_tokens_details")
    output_details = value.get("output_tokens_details")
    cached = input_details.get("cached_tokens", 0) if isinstance(input_details, dict) else 0
    reasoning = output_details.get("reasoning_tokens", 0) if isinstance(output_details, dict) else 0
    return ModelUsage(
        input_tokens,
        output_tokens,
        total_tokens,
        _nonnegative_int(cached, provider, "cached_tokens"),
        _nonnegative_int(reasoning, provider, "reasoning_tokens"),
    )


def _nonnegative_int(value: Any, provider: str, field: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise invalid_provider_response(provider, f"invalid {field}")
    return value


def _require_candidate(candidate: ModelCandidate, provider: str) -> None:
    if candidate.provider != provider:
        raise ValueError(f"{provider} adapter cannot invoke {candidate.provider} candidate")
