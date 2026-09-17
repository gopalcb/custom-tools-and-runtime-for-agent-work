"""
Shared compact runtime contracts.

These lightweight dataclasses keep runtime.py readable while avoiding a large
framework-style package layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RuntimeEvent:
    """One compact runtime event."""

    type: str
    run_id: str
    session_id: str
    agent_id: str
    status: str | None = None
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        """Return the event as JSON-compatible data."""
        return {
            "type": self.type,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "message": self.message,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass
class RunContext:
    """State for one compact agent runtime run."""

    project_root: Path
    run_id: str
    session_id: str
    agent_id: str
    prompt: str
    workflow_id: str = "analysis"
    events: list[RuntimeEvent] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def emit(self, event_type: str, status: str | None = None, message: str | None = None, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        """Append and return one runtime event."""
        event = RuntimeEvent(event_type, self.run_id, self.session_id, self.agent_id, status, message, dict(payload or {}))
        self.events.append(event)
        return event
