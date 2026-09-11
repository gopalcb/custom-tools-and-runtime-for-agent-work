#!/usr/bin/env python3
"""Fail fast when required monorepo agent services are not healthy."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def load_agent_monorepo(root: Path) -> None:
    """Load the source package without requiring an editable install."""
    if "agent_monorepo" in sys.modules:
        return
    package_dir = root / "agent-runtime" / "agent-monorepo"
    spec = importlib.util.spec_from_file_location(
        "agent_monorepo",
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load agent_monorepo from {package_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


def main() -> int:
    root = Path(os.environ.get("MONOREPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
    load_agent_monorepo(root)
    from agent_monorepo.system_health import run_monorepo_system_health

    result = run_monorepo_system_health(root)
    print(json.dumps({"status": result["status"], "checks": result["checks"]}, indent=2, sort_keys=True))
    return 0 if result["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
