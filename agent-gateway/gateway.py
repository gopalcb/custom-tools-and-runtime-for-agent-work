"""Stable external facade for the agent runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from agent_monorepo.events import RuntimeEvent

if TYPE_CHECKING:
    from agent_monorepo.runtime import AgentRuntime


class AgentGateway:
    """Expose live runs without taking ownership away from the runtime."""

    def __init__(self, runtime: "AgentRuntime") -> None:
        self.runtime = runtime

    async def run(
        self,
        prompt: str,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        resume: bool = False,
    ) -> AsyncIterator[RuntimeEvent]:
        """Stream runtime events for one prompt execution."""
        async for event in self.runtime.run(
            prompt,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            resume=resume,
        ):
            yield event

    async def cancel(self, run_id: str) -> bool:
        """Request cancellation of an active run."""
        return await self.runtime.cancel(run_id)

    async def respond_to_approval(self, request_id: int, decision: str) -> None:
        """Forward an approval decision to the runtime's Codex client."""
        await self.runtime.respond_to_approval(request_id, decision)

    async def run_command(self, command: str) -> dict:
        """Forward a Codex slash command without adding gateway logic."""
        return await self.runtime.run_command(command)

    async def close(self) -> None:
        """Close runtime resources owned by the gateway."""
        await self.runtime.close()
