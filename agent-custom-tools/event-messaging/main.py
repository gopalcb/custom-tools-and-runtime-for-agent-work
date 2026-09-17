"""
Command-line entry point for compact event messaging.

The CLI can send, inspect, process, fail, list messages, inspect tasks/errors,
and run the small polling hub without nested package directories.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bus import MessageBus
from hub import main as hub_main
from models import AgentMessage, MessageRecord


def payload_from_args(args: argparse.Namespace) -> dict:
    """Load a JSON payload from command arguments."""
    if getattr(args, "payload_file", None):
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if getattr(args, "payload_json", None):
        return json.loads(args.payload_json)
    return {}


def record_to_dict(record: MessageRecord) -> dict:
    """Return a printable record mapping."""
    return record.to_dict(include_payload=True)


def build_parser() -> argparse.ArgumentParser:
    """Create the event messaging CLI parser."""
    parser = argparse.ArgumentParser(description="Compact local event messaging")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("send")
    send.add_argument("--sender", required=True)
    send.add_argument("--recipient", required=True)
    send.add_argument("--type", required=True)
    send.add_argument("--payload-json")
    send.add_argument("--payload-file")
    pending = sub.add_parser("pending")
    pending.add_argument("--agent-id", required=True)
    process = sub.add_parser("process")
    process.add_argument("--agent-id", required=True)
    process.add_argument("--path", required=True)
    fail = sub.add_parser("fail")
    fail.add_argument("--agent-id", required=True)
    fail.add_argument("--path", required=True)
    fail.add_argument("--reason", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--agent-id")
    list_parser.add_argument("--status")
    list_parser.add_argument("--type")
    list_parser.add_argument("--limit", type=int)
    show = sub.add_parser("show")
    show.add_argument("message_id")
    thread = sub.add_parser("thread")
    thread.add_argument("message_id")
    sub.add_parser("summary")
    events = sub.add_parser("events")
    events.add_argument("--limit", type=int)
    sub.add_parser("tasks")
    sub.add_parser("current-error")
    resolve = sub.add_parser("resolve-error")
    resolve.add_argument("--status", choices=["fixed", "superseded"], default="fixed")
    hub = sub.add_parser("hub")
    hub.add_argument("hub_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one compact event messaging command."""
    args = build_parser().parse_args(argv)
    if args.command == "hub":
        return hub_main(["--root", args.root or "", *(args.hub_args or [])] if args.root else args.hub_args)
    bus = MessageBus(args.root)
    if args.command == "send":
        path = bus.send(AgentMessage(args.sender, args.recipient, args.type, payload_from_args(args)))
        result = {"path": str(path)}
    elif args.command == "pending":
        result = {"paths": [str(path) for path in bus.pending(args.agent_id)]}
    elif args.command == "process":
        result = {"path": str(bus.mark_processed(args.agent_id, args.path))}
    elif args.command == "fail":
        result = {"path": str(bus.mark_failed(args.agent_id, args.path, args.reason))}
    elif args.command == "list":
        result = {
            "records": [
                record_to_dict(record)
                for record in bus.list_records(args.agent_id, args.status, args.type, args.limit)
            ]
        }
    elif args.command == "show":
        result = record_to_dict(bus.read_record(args.message_id))
    elif args.command == "thread":
        result = {"records": [record_to_dict(record) for record in bus.thread(args.message_id)]}
    elif args.command == "summary":
        result = bus.summary()
    elif args.command == "events":
        result = {"events": bus.read_events(args.limit)}
    elif args.command == "tasks":
        result = {"tasks": bus.list_task_records()}
    elif args.command == "current-error":
        result = {"current_error": bus.read_current_error()}
    else:
        result = bus.resolve_current_error(args.status)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
