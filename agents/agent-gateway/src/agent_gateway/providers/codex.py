from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..models import AgentRunResult, LoadedAgent
from .base import AgentProvider


class CodexProvider(AgentProvider):
    """Codex runtime adapter using the official Python SDK.

    `openai-codex` is an optional dependency of agent-gateway so configuration,
    loading, and scaffolding can work without a Codex installation.
    """

    @staticmethod
    def _sdk():
        try:
            from openai_codex import Codex, Sandbox
        except ImportError as exc:
            raise RuntimeError(
                "Codex provider requires the optional dependency: "
                "pip install -e 'agents/agent-gateway[codex]'"
            ) from exc
        return Codex, Sandbox

    @staticmethod
    def _sandbox_value(sandbox_enum, configured: str):
        return {
            "read-only": sandbox_enum.read_only,
            "workspace-write": sandbox_enum.workspace_write,
            "full-access": sandbox_enum.full_access,
        }[configured]

    def run_new(self, agent: LoadedAgent, prompt: str, *, cwd: Path) -> AgentRunResult:
        run_id = f"run-{uuid4().hex[:12]}"
        try:
            Codex, Sandbox = self._sdk()
            with Codex() as codex:
                thread = codex.thread_start(
                    cwd=str(cwd),
                    developer_instructions=agent.instructions,
                    model=agent.spec.runtime.model,
                    sandbox=self._sandbox_value(Sandbox, agent.spec.runtime.sandbox),
                )
                result = thread.run(prompt)
                usage = getattr(result, "usage", None)
                if usage is not None and hasattr(usage, "model_dump"):
                    usage = usage.model_dump()
                return AgentRunResult(
                    run_id=run_id,
                    agent_id=agent.spec.id,
                    session_id=thread.id,
                    status="completed",
                    final_response=result.final_response or "",
                    token_usage=usage if isinstance(usage, dict) else None,
                )
        except Exception as exc:
            return AgentRunResult(
                run_id=run_id,
                agent_id=agent.spec.id,
                status="failed",
                error=str(exc),
            )

    def resume(self, agent: LoadedAgent, session_id: str, prompt: str, *, cwd: Path) -> AgentRunResult:
        run_id = f"run-{uuid4().hex[:12]}"
        try:
            Codex, Sandbox = self._sdk()
            with Codex() as codex:
                thread = codex.thread_resume(
                    session_id,
                    cwd=str(cwd),
                    developer_instructions=agent.instructions,
                    model=agent.spec.runtime.model,
                    sandbox=self._sandbox_value(Sandbox, agent.spec.runtime.sandbox),
                )
                result = thread.run(prompt)
                usage = getattr(result, "usage", None)
                if usage is not None and hasattr(usage, "model_dump"):
                    usage = usage.model_dump()
                return AgentRunResult(
                    run_id=run_id,
                    agent_id=agent.spec.id,
                    session_id=thread.id,
                    status="completed",
                    final_response=result.final_response or "",
                    token_usage=usage if isinstance(usage, dict) else None,
                )
        except Exception as exc:
            return AgentRunResult(
                run_id=run_id,
                agent_id=agent.spec.id,
                session_id=session_id,
                status="failed",
                error=str(exc),
            )
