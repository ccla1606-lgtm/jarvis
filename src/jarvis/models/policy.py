"""Logical model profiles, capability matrix, and deterministic routes."""

from dataclasses import dataclass
from enum import StrEnum

from jarvis.models.contracts import ModelProfile, ModelRequest
from jarvis.models.errors import ModelErrorCategory, ModelGatewayError


class StructuredOutputMode(StrEnum):
    NONE = "none"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    structured_output: StructuredOutputMode
    tool_calls: bool
    streaming: bool
    cancellation: bool
    reasoning_controls: bool
    context_window_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        if self.context_window_tokens < 1 or self.max_output_tokens < 1:
            raise ValueError("model token limits must be positive")

    def supports(self, request: ModelRequest, *, streaming: bool = False) -> bool:
        return (
            (
                request.output_schema is None
                or self.structured_output is not StructuredOutputMode.NONE
            )
            and (not request.tools or self.tool_calls)
            and (not streaming or (self.streaming and self.cancellation))
            and request.max_output_tokens <= self.max_output_tokens
        )


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    profile: ModelProfile
    provider: str
    model: str
    capabilities: ModelCapabilities
    account: str | None = None

    def __post_init__(self) -> None:
        if not self.provider or not self.model:
            raise ValueError("candidate provider and model must not be empty")


class ModelRouter:
    def __init__(self, routes: dict[ModelProfile, tuple[ModelCandidate, ...]]) -> None:
        missing = set(ModelProfile) - routes.keys()
        if missing:
            names = ", ".join(sorted(profile.value for profile in missing))
            raise ValueError(f"missing model routes: {names}")
        self._routes = {profile: tuple(candidates) for profile, candidates in routes.items()}
        if any(not candidates for candidates in self._routes.values()):
            raise ValueError("every model profile requires at least one candidate")

    def candidates(
        self,
        request: ModelRequest,
        *,
        streaming: bool = False,
    ) -> tuple[ModelCandidate, ...]:
        supported = tuple(
            candidate
            for candidate in self._routes[request.profile]
            if candidate.capabilities.supports(request, streaming=streaming)
        )
        if not supported:
            raise ModelGatewayError(
                ModelErrorCategory.CAPABILITY_MISMATCH,
                f"no configured model supports profile {request.profile.value}",
                retryable=False,
            )
        return supported


OPENAI_CAPABILITIES = ModelCapabilities(
    structured_output=StructuredOutputMode.JSON_SCHEMA,
    tool_calls=True,
    streaming=True,
    cancellation=True,
    reasoning_controls=True,
    context_window_tokens=1_050_000,
    max_output_tokens=128_000,
)

DEEPSEEK_CAPABILITIES = ModelCapabilities(
    structured_output=StructuredOutputMode.JSON_OBJECT,
    tool_calls=True,
    streaming=True,
    cancellation=True,
    reasoning_controls=True,
    context_window_tokens=1_000_000,
    max_output_tokens=384_000,
)


def default_router(
    *,
    openai_fast_model: str = "gpt-5.6-luna",
    openai_reasoning_model: str = "gpt-5.6-terra",
    deepseek_fast_model: str = "deepseek-v4-flash",
    deepseek_reasoning_model: str = "deepseek-v4-pro",
) -> ModelRouter:
    """Return production-shaped defaults isolated inside the model layer."""

    def candidates(
        profile: ModelProfile,
        openai_model: str,
        deepseek_model: str,
    ) -> tuple[ModelCandidate, ...]:
        return (
            ModelCandidate(profile, "openai", openai_model, OPENAI_CAPABILITIES),
            ModelCandidate(profile, "deepseek", deepseek_model, DEEPSEEK_CAPABILITIES),
        )

    return ModelRouter(
        {
            ModelProfile.FAST: candidates(
                ModelProfile.FAST,
                openai_fast_model,
                deepseek_fast_model,
            ),
            ModelProfile.PLANNER: candidates(
                ModelProfile.PLANNER,
                openai_reasoning_model,
                deepseek_reasoning_model,
            ),
            ModelProfile.CODER: candidates(
                ModelProfile.CODER,
                openai_reasoning_model,
                deepseek_reasoning_model,
            ),
            ModelProfile.REVIEWER: candidates(
                ModelProfile.REVIEWER,
                openai_reasoning_model,
                deepseek_reasoning_model,
            ),
            ModelProfile.SUMMARIZER: candidates(
                ModelProfile.SUMMARIZER,
                openai_fast_model,
                deepseek_fast_model,
            ),
        }
    )
