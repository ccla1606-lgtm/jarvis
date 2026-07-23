"""DeepSeek OpenAI-compatible Chat Completions adapter."""

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
from jarvis.models.contracts import ModelRequest, ModelUsage, ToolCall
from jarvis.models.policy import DEEPSEEK_CAPABILITIES, ModelCandidate, ModelCapabilities
from jarvis.models.ports import ProviderResult, ProviderStreamEvent


class DeepSeekAdapter(HttpModelAdapter):
    """Translate normalized contracts to DeepSeek's Chat Completions format."""

    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        base_url: str = "https://api.deepseek.com",
        capabilities: ModelCapabilities = DEEPSEEK_CAPABILITIES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            provider="deepseek",
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
        data = await self._post_json(
            "/chat/completions",
            payload=_request_payload(request, candidate.model, stream=False),
            timeout=request.timeout_seconds,
        )
        return _parse_response(data, self.provider)

    async def stream(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> AsyncIterator[ProviderStreamEvent]:
        _require_candidate(candidate, self.provider)
        pending_calls: dict[int, dict[str, str]] = {}
        async for event in self._stream_sse(
            "/chat/completions",
            payload=_request_payload(request, candidate.model, stream=True),
            timeout=request.timeout_seconds,
        ):
            usage_value = event.get("usage")
            if isinstance(usage_value, dict):
                yield ProviderStreamEvent(
                    kind="usage",
                    usage=_parse_usage(usage_value, self.provider),
                )
            choices = event.get("choices")
            if not isinstance(choices, list):
                continue
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    continue
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield ProviderStreamEvent(kind="text_delta", text=content)
                for tool_call in delta.get("tool_calls", []):
                    if isinstance(tool_call, dict):
                        _accumulate_tool_call(pending_calls, tool_call, self.provider)
        for index in sorted(pending_calls):
            yield ProviderStreamEvent(
                kind="tool_call",
                tool_call=_parse_accumulated_tool_call(
                    pending_calls[index],
                    self.provider,
                ),
            )
        yield stream_done()


def _request_payload(
    request: ModelRequest,
    model: str,
    *,
    stream: bool,
) -> dict[str, Any]:
    messages = [
        {
            "role": message.role.value,
            "content": message.content,
            **({"tool_call_id": message.tool_call_id} if message.tool_call_id is not None else {}),
        }
        for message in request.messages
    ]
    if request.output_schema is not None:
        schema_instruction = (
            "Return only a JSON object matching this JSON Schema: "
            f"{json.dumps(request.output_schema.schema, separators=(',', ':'))}"
        )
        messages.insert(0, {"role": "system", "content": schema_instruction})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": request.max_output_tokens,
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    if request.output_schema is not None:
        payload["response_format"] = {"type": "json_object"}
    if request.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "strict": True,
                },
            }
            for tool in request.tools
        ]
    return payload


def _parse_response(data: dict[str, Any], provider: str) -> ProviderResult:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise invalid_provider_response(provider, "missing choices")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise invalid_provider_response(provider, "missing message")
    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise invalid_provider_response(provider, "message content is not text")
    calls = message.get("tool_calls", [])
    if not isinstance(calls, list):
        raise invalid_provider_response(provider, "tool calls are not a list")
    tool_calls = tuple(_parse_tool_call(call, provider) for call in calls if isinstance(call, dict))
    finish = choice.get("finish_reason")
    normalized_finish = (
        "tool_calls"
        if finish == "tool_calls"
        else "length"
        if finish == "length"
        else "content_filter"
        if finish == "content_filter"
        else "stop"
        if finish == "stop"
        else "other"
    )
    return ProviderResult(
        content=content,
        tool_calls=tool_calls,
        usage=_parse_usage(data.get("usage"), provider),
        finish_reason=normalized_finish,
        provider_request_id=data.get("id") if isinstance(data.get("id"), str) else None,
    )


def _parse_tool_call(item: dict[str, Any], provider: str) -> ToolCall:
    identifier = item.get("id")
    function = item.get("function")
    if not isinstance(identifier, str) or not isinstance(function, dict):
        raise invalid_provider_response(provider, "invalid tool call")
    name = function.get("name")
    arguments = function.get("arguments", "{}")
    if not isinstance(name, str):
        raise invalid_provider_response(provider, "invalid tool call name")
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
    except ValueError as error:
        raise invalid_provider_response(provider, "invalid tool call arguments") from error
    if not isinstance(parsed, dict):
        raise invalid_provider_response(provider, "tool arguments must be an object")
    return ToolCall(identifier, name, parsed)


def _accumulate_tool_call(
    pending: dict[int, dict[str, str]],
    item: dict[str, Any],
    provider: str,
) -> None:
    index = item.get("index", 0)
    if not isinstance(index, int) or index < 0:
        raise invalid_provider_response(provider, "invalid streaming tool call index")
    current = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
    identifier = item.get("id")
    if isinstance(identifier, str):
        current["id"] = identifier
    function = item.get("function")
    if not isinstance(function, dict):
        return
    name = function.get("name")
    if isinstance(name, str):
        current["name"] = name
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        current["arguments"] += arguments


def _parse_accumulated_tool_call(
    item: dict[str, str],
    provider: str,
) -> ToolCall:
    try:
        arguments = json.loads(item["arguments"] or "{}")
    except ValueError as error:
        raise invalid_provider_response(
            provider,
            "invalid streaming tool call arguments",
        ) from error
    if not item["id"] or not item["name"] or not isinstance(arguments, dict):
        raise invalid_provider_response(provider, "incomplete streaming tool call")
    return ToolCall(item["id"], item["name"], arguments)


def _parse_usage(value: Any, provider: str) -> ModelUsage:
    if not isinstance(value, dict):
        raise invalid_provider_response(provider, "missing usage")
    input_tokens = _nonnegative_int(value.get("prompt_tokens"), provider, "prompt_tokens")
    output_tokens = _nonnegative_int(
        value.get("completion_tokens"),
        provider,
        "completion_tokens",
    )
    total_tokens = _nonnegative_int(value.get("total_tokens"), provider, "total_tokens")
    details = value.get("prompt_tokens_details")
    cached_tokens = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
    completion_details = value.get("completion_tokens_details")
    reasoning_tokens = (
        completion_details.get("reasoning_tokens", 0) if isinstance(completion_details, dict) else 0
    )
    return ModelUsage(
        input_tokens,
        output_tokens,
        total_tokens,
        _nonnegative_int(cached_tokens, provider, "cached_tokens"),
        _nonnegative_int(reasoning_tokens, provider, "reasoning_tokens"),
    )


def _nonnegative_int(value: Any, provider: str, field: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise invalid_provider_response(provider, f"invalid {field}")
    return value


def _require_candidate(candidate: ModelCandidate, provider: str) -> None:
    if candidate.provider != provider:
        raise ValueError(f"{provider} adapter cannot invoke {candidate.provider} candidate")
