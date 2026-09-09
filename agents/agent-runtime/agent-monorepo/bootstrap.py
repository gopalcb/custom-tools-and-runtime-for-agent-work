from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from resolver import ProjectResolutionError, resolve_project


def find_monorepo_root(start: Path | None = None) -> Path:
    """Walk upward until `project-registry.yaml` and `agents/` are found."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "project-registry.yaml").is_file() and (candidate / "agents").is_dir():
            return candidate
    raise RuntimeError("Could not locate monorepo root.")


def load_registry(root: Path) -> dict[str, Any]:
    with (root / "project-registry.yaml").open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if data.get("version") != 1:
        raise RuntimeError("Unsupported project-registry.yaml version.")
    return data


def bootstrap(prompt: str, active_project: str | None = None) -> dict[str, str]:
    root = find_monorepo_root()
    registry = load_registry(root)
    resolution = resolve_project(prompt, registry, active_project=active_project)

    # V1: the registered project directory is also the agent directory.
    agent_path = (root / resolution.path).resolve()
    if root not in agent_path.parents:
        raise RuntimeError("Resolved agent path escapes the monorepo root.")
    if not agent_path.is_dir():
        raise RuntimeError(f"Resolved agent path does not exist: {agent_path}")

    return {
        "project": resolution.project,
        "agent_id": resolution.project,
        "agent_path": str(agent_path),
        "reason": resolution.reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve the monorepo agent for a user prompt.")
    parser.add_argument("prompt", help="User request used for project resolution")
    parser.add_argument("--active-project", default=None)
    args = parser.parse_args()

    try:
        print(json.dumps(bootstrap(args.prompt, args.active_project), indent=2))
    except ProjectResolutionError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
