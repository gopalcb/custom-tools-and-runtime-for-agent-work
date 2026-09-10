"""Optional polling dispatcher for message handlers."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from .bus import MessageBus
from .models import AgentMessage

Handler = Callable[[AgentMessage], dict[str, Any]]

DEBUGGER_AGENT_ID = "angular-ui-debugger-agent"


class AgentHub:
    def __init__(self, bus: MessageBus | None = None) -> None:
        self.bus = bus or MessageBus()
        self.handlers: dict[tuple[str, str], Handler] = {}

    def register(self, recipient: str, message_type: str, handler: Handler) -> None:
        self.handlers[(recipient, message_type)] = handler

    def run_once(self, agent_ids: list[str] | None = None) -> int:
        targets = agent_ids or sorted({recipient for recipient, _ in self.handlers})
        processed = 0
        for agent_id in targets:
            for path in self.bus.pending(agent_id):
                message = self.bus.read(path)
                handler = self.handlers.get((message.recipient, message.type))
                if handler is None:
                    self.bus.mark_failed(agent_id, path, f"No handler for {message.recipient}:{message.type}")
                    processed += 1
                    continue
                try:
                    result = handler(message)
                    self.bus.mark_processed(agent_id, path)
                    self._reply(message, result)
                except Exception as exc:  # pragma: no cover - defensive hub boundary
                    self.bus.mark_failed(agent_id, path, repr(exc))
                    self._reply(message, {"ok": False, "error": repr(exc)})
                processed += 1
        return processed

    def listen(self, interval_seconds: float = 1.0, agent_ids: list[str] | None = None) -> None:
        while True:
            self.run_once(agent_ids)
            time.sleep(interval_seconds)

    def _reply(self, message: AgentMessage, result: dict[str, Any]) -> None:
        if not message.sender:
            return
        self.bus.send(
            AgentMessage(
                sender=message.recipient,
                recipient=message.sender,
                type=f"{message.type}.result",
                payload=result,
                reply_to=message.id,
            )
        )


def handle_ui_debug_request(message: AgentMessage) -> dict[str, Any]:
    try:
        from angular_ui_debugger.runner import DebugRequest, run_debug_request
    except ModuleNotFoundError as exc:
        if exc.name != "angular_ui_debugger":
            raise
        return {
            "ok": False,
            "request_id": message.payload.get("request_id"),
            "manifest_path": None,
            "artifact_dir": None,
            "summary": {
                "error_count": 1,
                "first_error": (
                    "angular-ui-debugger is not installed. Install it in the same "
                    "Python environment or include angular-ui-debugger/src on PYTHONPATH."
                ),
            },
        }

    request = DebugRequest.from_dict(message.payload)
    result = run_debug_request(request)
    return {
        "ok": result.ok,
        "request_id": result.request_id,
        "manifest_path": str(result.manifest_path),
        "artifact_dir": str(result.artifact_dir),
        "summary": _compact_summary(result.summary),
    }


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "requested_artifacts": summary.get("requested_artifacts"),
        "artifact_paths": summary.get("artifact_paths"),
        "inline_artifacts": summary.get("inline_artifacts"),
        "console_error_count": summary.get("console_error_count"),
        "network_issue_count": summary.get("network_issue_count"),
        "page_title": summary.get("page_title"),
    }
    errors = summary.get("errors") or []
    if errors:
        compact["error_count"] = len(errors)
        compact["first_error"] = str(errors[0])[:500]
    return compact


def build_default_hub(root: str | Path | None = None) -> AgentHub:
    hub = AgentHub(MessageBus(root))
    hub.register(DEBUGGER_AGENT_ID, "ui_debug_request", handle_ui_debug_request)
    return hub


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Codex agent message hub")
    parser.add_argument("--root", help="Message root. Defaults to .agent-state/agents-messaging.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-once")

    p_listen = sub.add_parser("listen")
    p_listen.add_argument("--interval", type=float, default=1.0)

    args = parser.parse_args(argv)
    hub = build_default_hub(args.root)
    if args.command == "run-once":
        print(hub.run_once())
        return 0
    if args.command == "listen":
        hub.listen(args.interval)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
