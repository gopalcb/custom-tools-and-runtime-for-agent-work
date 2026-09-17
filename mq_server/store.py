"""
Small file-backed store used by the compact MQ server.

The full monorepo controller-plane has richer stores; this version only keeps
event snapshots and task records needed by the compact runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class LocalStore:
    """Persist MQ events and task records under `.agent-state`."""

    def __init__(self, project_root: str | Path = ".") -> None:
        """Create a store rooted at one project."""
        self.project_root = Path(project_root).resolve()
        self.state_root = self.project_root / ".agent-state"

    def save_event(self, topic: str, event: Mapping[str, Any]) -> Path:
        """Persist the latest event state."""
        target = self.state_root / "messages" / f"events-{topic}" / f"{event['event_id']}.json"
        self.write_json(target, event)
        return target

    def save_task(self, project: str, task_id: str, record: Mapping[str, Any]) -> Path:
        """Persist a task record."""
        target = self.state_root / "task" / project / f"{task_id}.json"
        self.write_json(target, record)
        return target

    def write_json(self, path: Path, value: Mapping[str, Any]) -> None:
        """Write JSON with parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
