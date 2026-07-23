"""Deterministic provider used only by tests and local demos."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterable

from jarvis.models.contracts import ModelRequest
from jarvis.models.policy import ModelCandidate, ModelCapabilities
from jarvis.models.ports import ProviderResult, ProviderStreamEvent


class FakeProviderAdapter:
    def __init__(
        self,
        provider: str,
        *,
        capabilities: ModelCapabilities,
        results: Iterable[ProviderResult | Exception] = (),
        stream_events: Iterable[ProviderStreamEvent | Exception] = (),
    ) -> None:
        self._provider = provider
        self._capabilities = capabilities
        self._results = deque(results)
        self._stream_events = deque(stream_events)
        self.calls: list[tuple[ModelRequest, ModelCandidate]] = []
        self.closed = False

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    async def invoke(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> ProviderResult:
        self.calls.append((request, candidate))
        if not self._results:
            raise AssertionError("fake provider has no scripted result")
        result = self._results.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    async def stream(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
    ) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append((request, candidate))
        while self._stream_events:
            await asyncio.sleep(0)
            event = self._stream_events.popleft()
            if isinstance(event, Exception):
                raise event
            yield event

    async def aclose(self) -> None:
        self.closed = True
