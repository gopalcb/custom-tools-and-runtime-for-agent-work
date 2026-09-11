"""Legacy project-scoped entry point that now passes through to native Codex."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def configure_import_paths(root: Path) -> None:
    """Make source-layout packages importable when this file runs as a script."""
    for relative in (
        "agent-runtime",
        "agent-runtime/agent-monorepo",
        "agent-gateway",
        "agent-tools/internal-messaging",
    ):
        path = str(root / relative)
        if path not in sys.path:
            sys.path.insert(0, path)
    load_source_package("agent_monorepo", root / "agent-runtime" / "agent-monorepo")


def load_source_package(package_name: str, package_dir: Path) -> None:
    """Load a flat source-layout package directly from its package directory."""
    if package_name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        package_name,
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load package {package_name} from {package_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)


def run_native(native_codex: Path, args: list[str]) -> int:
    """Replace this launcher with native Codex and preserve its exit behavior."""
    completed = subprocess.run([str(native_codex), *args], check=False)
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    """Pass every invocation through to native Codex."""
    configure_import_paths(ROOT)

    from agent_monorepo.bootstrap import resolve_native_codex

    args = list(sys.argv[1:] if argv is None else argv)
    native_codex = resolve_native_codex(ROOT)
    os.environ["AGENT_MONOREPO_ROOT"] = str(ROOT)
    os.environ["CUSTOM_CODEX_BIN"] = str(ROOT / "bin" / "codex")
    os.environ["CODEX_NATIVE_BIN"] = str(native_codex)

    try:
        if args and args[0] == "native":
            return run_native(native_codex, args[1:])
        return run_native(native_codex, args)
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"Unable to start native Codex: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
