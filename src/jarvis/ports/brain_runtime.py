"""Replaceable runtime boundary for the Jarvis brain."""

from typing import Protocol

from jarvis.domain.ids import TaskId
from jarvis.graph.contracts import ApprovalSignal, BrainRequest, BrainResult


class BrainRuntimePort(Protocol):
    async def run(self, request: BrainRequest) -> BrainResult: ...

    async def resume(self, task_id: TaskId, signal: ApprovalSignal) -> BrainResult: ...

    def mermaid(self) -> str: ...
