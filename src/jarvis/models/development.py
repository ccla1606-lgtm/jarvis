"""Deterministic model adapter used by development and integration paths."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from jarvis.models.contracts import ModelMessage, ModelRequest, ModelUsage
from jarvis.models.policy import OPENAI_CAPABILITIES, ModelCandidate
from jarvis.models.ports import ProviderResult, ProviderStreamEvent

_MUTATING_WORDS = frozenset(
    {
        "apply",
        "change",
        "delete",
        "deploy",
        "edit",
        "execute",
        "modify",
        "remove",
        "run",
        "write",
    }
)


class DeterministicDevelopmentAdapter:
    """A bounded, provider-shaped adapter with no network or paid API calls."""

    provider = "development"
    capabilities = OPENAI_CAPABILITIES

    async def invoke(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> ProviderResult:
        del candidate
        if request.output_schema is not None:
            content = json.dumps(
                self._structured(request.output_schema.name, request.messages),
                separators=(",", ":"),
            )
        else:
            content = "Development model response: " + request.messages[-1].content
        input_tokens = max(1, sum(len(message.content) for message in request.messages) // 4)
        output_tokens = max(1, len(content) // 4)
        usage = ModelUsage(input_tokens, output_tokens, input_tokens + output_tokens)
        return ProviderResult(
            content=content,
            tool_calls=(),
            usage=usage,
            finish_reason="stop",
            provider_request_id=f"development:{request.request_id or 'request'}",
        )

    async def stream(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> AsyncIterator[ProviderStreamEvent]:
        result = await self.invoke(request, candidate)
        yield ProviderStreamEvent(kind="text_delta", text=result.content)
        yield ProviderStreamEvent(kind="usage", usage=result.usage)
        yield ProviderStreamEvent(kind="done")

    async def aclose(self) -> None:
        return None

    @staticmethod
    def _structured(name: str, messages: tuple[ModelMessage, ...]) -> dict[str, Any]:
        raw = messages[-1].content
        if name == "triage_decision":
            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                request = {"objective": raw, "side_effects_allowed": False}
            objective = str(request.get("objective", raw))
            words = set(objective.lower().replace("/", " ").split())
            requires_side_effects = bool(words & _MUTATING_WORDS)
            route = "planned" if requires_side_effects else "fast"
            return {
                "route": route,
                "rationale": (
                    "mutation requires approval"
                    if requires_side_effects
                    else "read-only request fits the fast path"
                ),
                "estimated_steps": 2 if requires_side_effects else 1,
                "requires_side_effects": requires_side_effects,
            }
        if name == "execution_plan":
            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                request = {}
            return {
                "steps": [
                    {
                        "position": 1,
                        "description": "Execute the approved objective",
                        "depends_on": [],
                        "tools": list(request.get("allowed_tools", [])),
                        "repositories": list(request.get("allowed_repositories", [])),
                    }
                ]
            }
        return {"result": "ok"}
