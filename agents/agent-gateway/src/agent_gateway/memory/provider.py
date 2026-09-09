from __future__ import annotations

from typing import Protocol


class MemoryProvider(Protocol):
    def retrieve(self, agent_id: str, query: str, limit: int = 5) -> list[dict]: ...
    def store(self, agent_id: str, memory: dict) -> None: ...


class NoOpMemoryProvider:
    """V1 default. The long-term/semantic memory layer is intentionally deferred."""

    def retrieve(self, agent_id: str, query: str, limit: int = 5) -> list[dict]:
        return []

    def store(self, agent_id: str, memory: dict) -> None:
        return None
