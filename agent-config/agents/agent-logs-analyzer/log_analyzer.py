"""Watch system diagnostic logs and route ERROR lines to messaging.

This module owns the background log tailer for the log analyzer agent. It
observes fresh .agent-state system log lines and passes exact error objects to
the shared messaging bus for tracking and escalation.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_monorepo.events import EventHub
from agents_internal_messaging.bus import MessageBus


AGENT_ID = "agent-logs-analyzer"
SESSION_ID = "system-log-analyzer"
ERROR_MARKER = "ERROR"
DEFAULT_POLL_INTERVAL = 1.0
MAX_CONTEXT_LINES = 8
MAX_ERROR_LENGTH = 600

logger = logging.getLogger(__name__)
RUNNERS: dict[Path, "LogAnalyzer"] = {}
RUNNERS_LOCK = threading.Lock()


@dataclass
class LogAnalyzer:
    """Long-running tailer for .agent-state system log files."""

    project_root: Path
    state_root: Path
    messaging_root: Path | None = None
    poll_interval: float = DEFAULT_POLL_INTERVAL
    positions: dict[Path, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize paths and create the thread controls."""
        self.project_root = self.project_root.resolve()
        self.state_root = self.state_root.resolve()
        self.logs_root = self.state_root / "logs" / "system"
        self.messaging_root = (
            self.messaging_root.resolve()
            if self.messaging_root is not None
            else self.state_root / "agents-messaging"
        )
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self.run,
            name=f"{AGENT_ID}-{self.project_root.name}",
            daemon=True,
        )

    def start(self) -> None:
        """Start the analyzer thread if it is not already alive."""
        if self.thread.is_alive():
            return
        self.prepare()
        self.thread.start()

    def prepare(self) -> None:
        """Create analyzer directories and position existing logs at EOF."""
        if not self.project_root.exists():
            return
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.discover_log_files(initial=True)

    def is_running(self) -> bool:
        """Return whether the analyzer thread is alive."""
        return self.thread.is_alive()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the analyzer thread to stop and wait briefly."""
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=timeout)

    def run(self) -> None:
        """Tail new system log lines until stopped or the project root disappears."""
        if not self.project_root.exists():
            return
        project_available = True
        self.emit_background_event("background.started", "Log analyzer started", {})

        while not self.stop_event.wait(self.poll_interval):
            if not self.project_root.exists():
                project_available = False
                break
            try:
                self.scan_once()
            except Exception as error:
                logger.warning("Log analyzer scan failed: %s", error)

        if project_available and self.project_root.exists():
            self.emit_background_event("background.completed", "Log analyzer stopped", {})

    def scan_once(self) -> None:
        """Scan existing and newly created system log files for fresh ERROR lines."""
        self.discover_log_files(initial=False)
        for log_path in sorted(self.positions):
            if not log_path.exists() or not log_path.is_file():
                continue
            previous_position = self.positions[log_path]
            size = log_path.stat().st_size
            if size < previous_position:
                previous_position = 0
            if size == previous_position:
                continue
            lines = self.read_new_lines(log_path, previous_position)
            self.positions[log_path] = log_path.stat().st_size
            for line_number, line in lines:
                if ERROR_MARKER in line:
                    self.handle_error_line(log_path, line_number, line)

    def discover_log_files(self, initial: bool) -> None:
        """Track current system log files and initialize read offsets."""
        if not self.logs_root.exists():
            return
        for path in sorted(self.logs_root.rglob("*.log")):
            if not path.is_file() or path in self.positions:
                continue
            self.positions[path] = path.stat().st_size if initial else 0

    def read_new_lines(self, log_path: Path, start: int) -> list[tuple[int, str]]:
        """Read new lines from one log file starting at a byte offset."""
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(start)
            first_line_number = self.count_lines_before(log_path, start) + 1
            return [
                (first_line_number + index, line.rstrip("\n"))
                for index, line in enumerate(handle.readlines())
            ]

    def count_lines_before(self, log_path: Path, offset: int) -> int:
        """Count complete lines before an offset for stable line numbers."""
        if offset <= 0:
            return 0
        count = 0
        with log_path.open("rb") as handle:
            remaining = offset
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                count += chunk.count(b"\n")
                remaining -= len(chunk)
        return count

    def handle_error_line(self, log_path: Path, line_number: int, line: str) -> None:
        """Send one exact log error object to the messaging error tracker."""
        error_object = build_log_error_object(
            self.project_root,
            log_path,
            line_number,
            line,
            self.load_context(log_path, line_number),
        )
        record = MessageBus(self.messaging_root).record_error(error_object)
        self.emit_background_event(
            "error",
            line[:MAX_ERROR_LENGTH],
            {
                "error": error_object,
                "current_error_path": str(MessageBus(self.messaging_root).current_error_path()),
                "fingerprint": record.get("fingerprint"),
            },
            status="detected",
        )

    def load_context(self, log_path: Path, line_number: int) -> list[str]:
        """Load nearby raw log lines around an error."""
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        start = max(0, line_number - MAX_CONTEXT_LINES - 1)
        end = min(len(lines), line_number + MAX_CONTEXT_LINES)
        return [
            f"{index + 1}: {lines[index][:MAX_ERROR_LENGTH]}"
            for index in range(start, end)
        ]

    def emit_background_event(
        self,
        event_type: str,
        message: str,
        payload: dict[str, Any],
        status: str = "completed",
    ) -> None:
        """Emit one durable RuntimeEvent for the background analyzer run."""
        run_id = f"log-analyzer-{datetime.now(timezone.utc).date().isoformat()}"
        try:
            hub = EventHub(self.state_root)
            asyncio.run(
                hub.emit(
                    hub.new_event(
                        event_type,
                        run_id=run_id,
                        session_id=SESSION_ID,
                        agent_id=AGENT_ID,
                        status=status,
                        message=message,
                        payload=payload,
                    )
                )
            )
        except Exception as error:
            logger.warning("Log analyzer could not emit %s: %s", event_type, error)


def build_log_error_object(
    project_root: Path,
    log_path: Path,
    line_number: int,
    line: str,
    context: list[str],
) -> dict[str, Any]:
    """Build the exact error object passed to the messaging bus."""
    return {
        "type": "log.error",
        "source": AGENT_ID,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "log_path": str(log_path.relative_to(project_root)),
        "line_number": line_number,
        "line": line[:MAX_ERROR_LENGTH],
        "context": context,
    }


def ensure_log_analyzer_running(
    project_root: str | Path,
    state_root: str | Path,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    messaging_root: str | Path | None = None,
) -> bool:
    """Ensure one analyzer thread is running for the project root."""
    root = Path(project_root).resolve()
    state = Path(state_root).resolve()
    messages = Path(messaging_root).resolve() if messaging_root is not None else None
    with RUNNERS_LOCK:
        runner = RUNNERS.get(root)
        if runner is not None and runner.is_running():
            return False
        runner = LogAnalyzer(root, state, messaging_root=messages, poll_interval=poll_interval)
        RUNNERS[root] = runner
        runner.start()
        return True


def is_log_analyzer_running(project_root: str | Path) -> bool:
    """Return whether the analyzer is alive for a project root."""
    root = Path(project_root).resolve()
    with RUNNERS_LOCK:
        runner = RUNNERS.get(root)
        return bool(runner and runner.is_running())


def stop_log_analyzer(project_root: str | Path | None = None) -> None:
    """Stop analyzer threads for one project root or for all roots."""
    root = Path(project_root).resolve() if project_root is not None else None
    with RUNNERS_LOCK:
        items = list(RUNNERS.items())
    for runner_root, runner in items:
        if root is not None and runner_root != root:
            continue
        runner.stop()
        with RUNNERS_LOCK:
            RUNNERS.pop(runner_root, None)
