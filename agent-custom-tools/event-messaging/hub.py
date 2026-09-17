"""
Runs a small polling hub over the compact event-messaging bus.

Handlers are registered by recipient and message type; results are returned as
reply messages so callers can inspect the same durable state tree.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from bus import MessageBus
from models import AgentMessage


Handler = Callable[[AgentMessage], dict[str, Any]]


class AgentHub:
    """Poll inboxes and dispatch messages to registered handlers."""

    def __init__(self, bus: MessageBus | None = None) -> None:
        """Create a hub over a message bus."""
        self.bus = bus or MessageBus()
        self.handlers: dict[tuple[str, str], Handler] = {}

    def register(self, recipient: str, message_type: str, handler: Handler) -> None:
        """Register one deterministic handler."""
        self.handlers[(recipient, message_type)] = handler

    def run_once(self, agent_ids: list[str] | None = None) -> int:
        """Process pending messages once and return the count handled."""
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
                    self.reply(message, result)
                except Exception as error:
                    self.bus.mark_failed(agent_id, path, repr(error))
                    self.reply(message, {"ok": False, "error": repr(error)})
                processed += 1
        return processed

    def listen(self, interval_seconds: float = 1.0, agent_ids: list[str] | None = None) -> None:
        """Poll forever until interrupted."""
        while True:
            self.run_once(agent_ids)
            time.sleep(interval_seconds)

    def reply(self, message: AgentMessage, result: dict[str, Any]) -> None:
        """Send a reply message to the original sender."""
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


def build_default_hub(root: str | Path | None = None) -> AgentHub:
    """Build the default compact hub with a health handler."""
    hub = AgentHub(MessageBus(root))
    hub.register("agent-health", "health.request", lambda message: {"ok": True, "payload": message.payload})
    return hub


def main(argv: list[str] | None = None) -> int:
    """Run the compact hub CLI."""
    parser = argparse.ArgumentParser(description="Compact local agent message hub")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-once")
    listen = sub.add_parser("listen")
    listen.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    hub = build_default_hub(args.root)
    if args.command == "run-once":
        print(json.dumps({"processed": hub.run_once()}, indent=2, sort_keys=True))
        return 0
    hub.listen(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
