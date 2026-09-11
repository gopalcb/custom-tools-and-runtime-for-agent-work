"""Check monorepo control-plane health before agent work starts.

This module owns the pre-work health check used by the runtime hook and CLI.
Runtime execution stays in runtime.py, while durable message/error tracking
stays in agents_internal_messaging.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

try:
    from agents_internal_messaging.bus import MessageBus
except ModuleNotFoundError:
    source_root = Path(__file__).resolve().parents[2] / "agent-tools" / "internal-messaging"
    sys.path.insert(0, str(source_root))
    from agents_internal_messaging.bus import MessageBus


def run_monorepo_system_health(
    project_root: str | Path,
    state_root: str | Path | None = None,
    messaging_root: str | Path | None = None,
    memory_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify required local agent services and write the latest health artifact."""
    root = Path(project_root).resolve()
    state = Path(state_root).resolve() if state_root else root / ".agent-state"
    messaging = Path(messaging_root).resolve() if messaging_root else state / "agents-messaging"
    memory = Path(memory_root).resolve() if memory_root else state / "cache" / "memory"
    checks: list[dict[str, Any]] = []

    checks.append(path_check(root / "project-registry.yaml", "project-registry", "file"))
    checks.append(path_check(root / "agent-config" / "agents", "agent-definitions", "directory"))
    checks.append(writable_directory_check(state / "logs", "runtime-session-logs"))
    checks.append(writable_directory_check(state / "sessions", "runtime-sessions"))
    checks.append(writable_directory_check(state / "logs" / "system" / "runtime", "runtime-diagnostics"))
    checks.append(writable_directory_check(state / "logs" / "system" / "messaging", "messaging-diagnostics"))
    checks.append(writable_directory_check(state / "logs" / "system" / "controller", "controller-diagnostics"))
    checks.append(writable_directory_check(memory / "records", "memory-records"))
    checks.append(log_analyzer_check(root))
    checks.extend(messaging_checks(messaging))

    status = "healthy" if all(check["status"] == "healthy" for check in checks) else "unhealthy"
    result = {
        "status": status,
        "project_root": str(root),
        "state_root": str(state),
        "messaging_root": str(messaging),
        "memory_root": str(memory),
        "checks": checks,
    }
    write_json(state / "logs" / "system" / "health" / "latest.json", result)
    if status != "healthy":
        bus = MessageBus(messaging)
        bus.record_error(
            {
                "type": "monorepo_system_health.failed",
                "status": status,
                "project_root": str(root),
                "checks": [check for check in checks if check["status"] != "healthy"],
            }
        )
    return result


def path_check(path: Path, name: str, expected: str) -> dict[str, Any]:
    """Check that a required file or directory exists."""
    exists = path.is_file() if expected == "file" else path.is_dir()
    return {
        "name": name,
        "status": "healthy" if exists else "unhealthy",
        "path": str(path),
        "expected": expected,
        "message": "available" if exists else f"missing required {expected}",
    }


def writable_directory_check(path: Path, name: str) -> dict[str, Any]:
    """Check that a required directory can be created and written."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".health-check.tmp"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        return {
            "name": name,
            "status": "unhealthy",
            "path": str(path),
            "message": str(error),
        }
    return {"name": name, "status": "healthy", "path": str(path), "message": "writable"}


def log_analyzer_check(root: Path) -> dict[str, Any]:
    """Require the log analyzer program only when that agent is configured."""
    agent_dir = root / "agent-config" / "agents" / "agent-logs-analyzer"
    program = agent_dir / "log_analyzer.py"
    if not agent_dir.exists():
        return {
            "name": "log-analyzer-program",
            "status": "healthy",
            "path": str(program),
            "message": "not configured",
        }
    return path_check(program, "log-analyzer-program", "file")


def messaging_checks(root: Path) -> list[dict[str, Any]]:
    """Check that internal messaging and error tracking are available."""
    checks: list[dict[str, Any]] = []
    try:
        bus = MessageBus(root)
        summary = bus.summary()
        checks.append({"name": "internal-messaging", "status": "healthy", "path": str(root), "message": "ready"})
        checks.append(path_check(bus.manifest_path(), "messaging-manifest", "file"))
        checks.append(path_check(bus.event_log_path(), "messaging-event-log", "file"))
        checks.append(path_check(bus.errors_dir(), "messaging-error-archive", "directory"))
        checks.append({
            "name": "messaging-error-tracker",
            "status": "healthy",
            "path": str(bus.current_error_path()),
            "message": f"current_error={bool(summary.get('current_error'))}",
        })
    except Exception as error:
        checks.append({
            "name": "internal-messaging",
            "status": "unhealthy",
            "path": str(root),
            "message": str(error),
        })
    return checks


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write one JSON document atomically enough for local health artifacts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Run the monorepo health check from the command line."""
    parser = argparse.ArgumentParser(description="Check local agent-monorepo health.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--state-root")
    parser.add_argument("--messaging-root")
    parser.add_argument("--memory-root")
    args = parser.parse_args(argv)
    result = run_monorepo_system_health(
        args.project_root,
        state_root=args.state_root,
        messaging_root=args.messaging_root,
        memory_root=args.memory_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
