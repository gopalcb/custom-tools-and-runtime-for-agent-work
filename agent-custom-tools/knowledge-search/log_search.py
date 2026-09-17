"""
Searches local logs and detects error records for compact agent workflows.

This file keeps the useful behavior of the log analyzer without running a
background thread: scan logs on demand, return matches, and optionally record
current errors through the compact event-messaging bus.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ERROR_MARKER = "ERROR"
MAX_CONTEXT_LINES = 8
MAX_ERROR_LENGTH = 600


def iter_log_files(root: str | Path) -> list[Path]:
    """Return visible log files below a root."""
    base = Path(root)
    if base.is_file():
        return [base]
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.log") if path.is_file())


def search_logs(root: str | Path = ".agent-state/logs", query: str = "", limit: int = 50) -> dict:
    """Search log files for a text or regular-expression query."""
    pattern = re.compile(query, re.IGNORECASE) if query else None
    matches = []
    for path in iter_log_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines, start=1):
            if pattern is None or pattern.search(line):
                matches.append({"path": str(path), "line_number": index, "line": line[:MAX_ERROR_LENGTH]})
                if len(matches) >= limit:
                    return {"root": str(root), "query": query, "matches": matches}
    return {"root": str(root), "query": query, "matches": matches}


def build_log_error_object(project_root: str | Path, log_path: Path, line_number: int, line: str, context: list[str]) -> dict:
    """Build the exact error object shape used by compact messaging."""
    try:
        relative = str(log_path.resolve().relative_to(Path(project_root).resolve()))
    except ValueError:
        relative = str(log_path)
    return {
        "type": "log.error",
        "source": "compact-log-search",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "log_path": relative,
        "line_number": line_number,
        "line": line[:MAX_ERROR_LENGTH],
        "context": context,
    }


def detect_log_errors(project_root: str | Path = ".", logs_root: str | Path = ".agent-state/logs/system", limit: int = 20) -> dict:
    """Find ERROR lines and return structured error objects."""
    errors = []
    for path in iter_log_files(Path(project_root) / logs_root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines, start=1):
            if ERROR_MARKER not in line:
                continue
            start = max(0, index - MAX_CONTEXT_LINES - 1)
            end = min(len(lines), index + MAX_CONTEXT_LINES)
            context = [f"{line_index + 1}: {lines[line_index][:MAX_ERROR_LENGTH]}" for line_index in range(start, end)]
            errors.append(build_log_error_object(project_root, path, index, line, context))
            if len(errors) >= limit:
                return {"errors": errors}
    return {"errors": errors}


def record_detected_errors(project_root: str | Path = ".", logs_root: str | Path = ".agent-state/logs/system", messaging_root: str | Path | None = None) -> dict:
    """Record detected errors through compact event messaging when available."""
    messaging_dir = Path(__file__).resolve().parents[1] / "event-messaging"
    if str(messaging_dir) not in sys.path:
        sys.path.insert(0, str(messaging_dir))
    from bus import MessageBus

    detected = detect_log_errors(project_root, logs_root)
    bus = MessageBus(messaging_root or Path(project_root) / ".agent-state" / "agents-messaging")
    records = [bus.record_error(error) for error in detected["errors"]]
    return {"recorded": len(records), "records": records}


def main(argv: list[str] | None = None) -> int:
    """Run compact log search from the command line."""
    parser = argparse.ArgumentParser(description="Search local logs")
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("find")
    find.add_argument("--root", default=".agent-state/logs")
    find.add_argument("--query", default="")
    find.add_argument("--limit", type=int, default=50)
    errors = sub.add_parser("errors")
    errors.add_argument("--project-root", default=".")
    errors.add_argument("--logs-root", default=".agent-state/logs/system")
    errors.add_argument("--limit", type=int, default=20)
    record = sub.add_parser("record-errors")
    record.add_argument("--project-root", default=".")
    record.add_argument("--logs-root", default=".agent-state/logs/system")
    record.add_argument("--messaging-root")
    args = parser.parse_args(argv)
    if args.command == "find":
        result = search_logs(args.root, args.query, args.limit)
    elif args.command == "errors":
        result = detect_log_errors(args.project_root, args.logs_root, args.limit)
    else:
        result = record_detected_errors(args.project_root, args.logs_root, args.messaging_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
