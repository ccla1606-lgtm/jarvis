"""Ports at the model boundary."""

from collections.abc import AsyncIterator
from typing import Protocol

from jarvis.models.contracts import (
    ModelRequest,
    ModelResponse,
    ModelUsage,
    StreamEvent,
    ToolCall,
)
from jarvis.models.policy import ModelCandidate, ModelCapabilities


class ModelPort(Protocol):
    async def invoke(self, request: ModelRequest) -> ModelResponse:
        """Return one normalized model response."""

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        """Stream normalized events and release resources on cancellation."""


class ProviderResult:
    """Internal normalized result; raw provider objects never cross this boundary."""

    __slots__ = (
        "content",
        "finish_reason",
        "provider_request_id",
        "tool_calls",
        "usage",
    )

    def __init__(
        self,
        *,
        content: str,
        tool_calls: tuple[ToolCall, ...],
        usage: ModelUsage,
        finish_reason: str,
        provider_request_id: str | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.usage = usage
        self.finish_reason = finish_reason
        self.provider_request_id = provider_request_id


class ProviderStreamEvent:
    __slots__ = ("kind", "text", "tool_call", "usage")

    def __init__(
        self,
        *,
        kind: str,
        text: str = "",
        tool_call: ToolCall | None = None,
        usage: ModelUsage | None = None,
    ) -> None:
        self.kind = kind
        self.text = text
        self.tool_call = tool_call
        self.usage = usage


class ProviderAdapter(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def invoke(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> ProviderResult: ...

    def stream(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> AsyncIterator[ProviderStreamEvent]: ...

    async def aclose(self) -> None: ...
