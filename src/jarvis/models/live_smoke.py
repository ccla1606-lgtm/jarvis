"""Explicit, credential-backed smoke calls excluded from default CI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime

from jarvis.models.adapters import DeepSeekAdapter, OpenAIResponsesAdapter
from jarvis.models.contracts import MessageRole, ModelMessage, ModelProfile, ModelRequest
from jarvis.models.gateway import ModelGateway
from jarvis.models.policy import (
    DEEPSEEK_CAPABILITIES,
    OPENAI_CAPABILITIES,
    ModelCandidate,
    ModelRouter,
)
from jarvis.models.ports import ProviderAdapter


def _single_provider_router(candidate: ModelCandidate) -> ModelRouter:
    return ModelRouter(
        {
            profile: (
                ModelCandidate(
                    profile,
                    candidate.provider,
                    candidate.model,
                    candidate.capabilities,
                    candidate.account,
                ),
            )
            for profile in ModelProfile
        }
    )


async def _call_provider(
    *,
    provider: str,
    model: str,
    api_key: str,
) -> dict[str, object]:
    adapter: ProviderAdapter
    if provider == "openai":
        adapter = OpenAIResponsesAdapter(api_key)
        capabilities = OPENAI_CAPABILITIES
    elif provider == "deepseek":
        adapter = DeepSeekAdapter(api_key)
        capabilities = DEEPSEEK_CAPABILITIES
    else:
        raise ValueError("unsupported live smoke provider")

    candidate = ModelCandidate(ModelProfile.FAST, provider, model, capabilities)
    gateway = ModelGateway(
        router=_single_provider_router(candidate),
        adapters={provider: adapter},
        max_retries_per_candidate=0,
        max_structured_repairs=0,
    )
    try:
        response = await gateway.invoke(
            ModelRequest(
                ModelProfile.FAST,
                (
                    ModelMessage(
                        MessageRole.USER,
                        "Reply with exactly the word JARVIS.",
                    ),
                ),
                max_output_tokens=16,
                timeout_seconds=30,
                request_id=f"live-smoke-{provider}",
            )
        )
    finally:
        await gateway.aclose()

    return {
        "provider": response.resolution.provider,
        "model": response.resolution.model,
        "timestamp": datetime.now(UTC).isoformat(),
        "content_sha256": hashlib.sha256(response.content.encode()).hexdigest(),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "status": "passed",
    }


async def _main() -> int:
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    missing = [
        name
        for name, value in (
            ("OPENAI_API_KEY", openai_key),
            ("DEEPSEEK_API_KEY", deepseek_key),
        )
        if not value
    ]
    if missing:
        print(
            f"BLOCKED: missing credentials: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    results = [
        await _call_provider(
            provider="openai",
            model=os.environ.get("JARVIS_OPENAI_MODEL", "gpt-5.6-luna"),
            api_key=openai_key,
        ),
        await _call_provider(
            provider="deepseek",
            model=os.environ.get("JARVIS_DEEPSEEK_MODEL", "deepseek-v4-flash"),
            api_key=deepseek_key,
        ),
    ]
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
