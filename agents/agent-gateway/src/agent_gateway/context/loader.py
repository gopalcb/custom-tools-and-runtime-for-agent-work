from __future__ import annotations

from pathlib import Path


def load_optional_context(agent_root: Path, filename: str = "PROJECT_CONTEXT.md") -> str:
    path = agent_root / filename
    return path.read_text(encoding="utf-8") if path.is_file() else ""
