from __future__ import annotations

from pathlib import Path


def resolve_skill_file(agents_root: Path, skill_id: str) -> Path | None:
    """Resolve a unique SKILL.md under agents/skills by leaf directory name."""
    matches = [path for path in (agents_root / "skills").glob(f"**/{skill_id}/SKILL.md")]
    if len(matches) == 1:
        return matches[0]
    return None
