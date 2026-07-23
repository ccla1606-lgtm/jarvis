"""Normalized contracts shared by every model provider."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any

JsonObject = dict[str, Any]


class ModelProfile(StrEnum):
    """Logical roles selected by application code."""

    FAST = "fast"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    SUMMARIZER = "summarizer"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(StrEnum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    OTHER = "other"


class StreamEventKind(StrEnum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: MessageRole
    content: str
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("message content must not be empty")
        if self.role is MessageRole.TOOL and not self.tool_call_id:
            raise ValueError("tool messages require tool_call_id")
        if self.role is not MessageRole.TOOL and self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid for tool messages")


@dataclass(frozen=True, slots=True)
class OutputSchema:
    """Requested structured output, expressed as provider-neutral JSON Schema."""

    name: str
    schema: JsonObject

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError("schema name must contain only letters, numbers, and underscores")
        if self.schema.get("type") != "object":
            raise ValueError("output schema root must be an object")
        object.__setattr__(self, "schema", dict(self.schema))


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: JsonObject

    def __post_init__(self) -> None:
        normalized = self.name.replace("_", "").replace("-", "")
        if not self.name or len(self.name) > 64 or not normalized.isalnum():
            raise ValueError("tool name is invalid")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        if self.parameters.get("type") != "object":
            raise ValueError("tool parameters root must be an object")
        object.__setattr__(self, "parameters", dict(self.parameters))


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: JsonObject

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("tool call id and name must not be empty")
        object.__setattr__(self, "arguments", dict(self.arguments))


@dataclass(frozen=True, slots=True)
class ModelRequest:
    profile: ModelProfile
    messages: tuple[ModelMessage, ...]
    max_output_tokens: int = 1024
    timeout_seconds: float = 30.0
    output_schema: OutputSchema | None = None
    tools: tuple[ToolDefinition, ...] = ()
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("model request requires at least one message")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.request_id is not None and not self.request_id.strip():
            raise ValueError("request_id must not be blank")

    def for_repair(self, *, invalid_output: str, validation_error: str) -> ModelRequest:
        """Append a bounded, provider-neutral request to repair one invalid result."""

        repair = ModelMessage(
            MessageRole.USER,
            (
                "Return only JSON matching the requested schema. "
                f"The previous result was invalid ({validation_error[:240]}). "
                f"Previous result: {invalid_output[:2000]}"
            ),
        )
        return replace(self, messages=(*self.messages, repair))


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.output_tokens,
            self.total_tokens,
            self.cached_input_tokens,
            self.reasoning_tokens,
        )
        if any(value < 0 for value in values):
            raise ValueError("token usage cannot be negative")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens cannot be smaller than input plus output")


@dataclass(frozen=True, slots=True)
class Resolution:
    """Auditable record of the concrete provider selected for one attempt."""

    profile: ModelProfile
    provider: str
    model: str
    account: str | None
    attempt: int
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider or not self.model:
            raise ValueError("resolution provider and model must not be empty")
        if self.attempt < 1:
            raise ValueError("resolution attempt must be positive")


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    structured_data: JsonObject | None
    tool_calls: tuple[ToolCall, ...]
    usage: ModelUsage
    resolution: Resolution
    finish_reason: FinishReason
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        if self.structured_data is not None:
            object.__setattr__(
                self,
                "structured_data",
                dict(self.structured_data),
            )


@dataclass(frozen=True, slots=True)
class StreamEvent:
    kind: StreamEventKind
    resolution: Resolution
    text: str = ""
    tool_call: ToolCall | None = None
    usage: ModelUsage | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        if self.kind is StreamEventKind.TEXT_DELTA and not self.text:
            raise ValueError("text delta event requires text")
        if self.kind is StreamEventKind.TOOL_CALL and self.tool_call is None:
            raise ValueError("tool call event requires a tool call")
        if self.kind is StreamEventKind.USAGE and self.usage is None:
            raise ValueError("usage event requires usage")
