from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import AgentRunResult, LoadedAgent


class AgentProvider(ABC):
    @abstractmethod
    def run_new(self, agent: LoadedAgent, prompt: str, *, cwd: Path) -> AgentRunResult:
        raise NotImplementedError

    @abstractmethod
    def resume(self, agent: LoadedAgent, session_id: str, prompt: str, *, cwd: Path) -> AgentRunResult:
        raise NotImplementedError
