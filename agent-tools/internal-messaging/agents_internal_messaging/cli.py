"""Command-line interface for sending and inspecting agent messages."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from textwrap import shorten

from .bus import MessageBus
from .logging_config import configure_messaging_logging
from .models import AgentMessage, MessageRecord


logger = logging.getLogger(__name__)


def _payload(args: argparse.Namespace) -> dict:
    if args.payload_file:
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if args.payload_json:
        return json.loads(args.payload_json)
    return {}


def _details(args: argparse.Namespace) -> dict:
    if args.details_file:
        return json.loads(Path(args.details_file).read_text(encoding="utf-8"))
    if args.details_json:
        return json.loads(args.details_json)
    return {}


def _record_dict(record: MessageRecord) -> dict:
    return record.to_dict(include_payload=True)


def _print_records(records: list[MessageRecord]) -> None:
    if not records:
        return
    print(f"{'STATUS':<10} {'CREATED':<22} {'FROM':<24} {'TO':<28} {'TYPE':<24} ID")
    for record in records:
        message = record.message
        created = message.created_at.replace("T", " ").replace("Z", "")
        print(
            f"{record.status:<10} "
            f"{created[:22]:<22} "
            f"{shorten(message.sender, width=24, placeholder='...'):<24} "
            f"{shorten(message.recipient, width=28, placeholder='...'):<28} "
            f"{shorten(message.type, width=24, placeholder='...'):<24} "
            f"{message.id}"
        )


def main(argv: list[str] | None = None) -> int:
    configure_messaging_logging()
    parser = argparse.ArgumentParser(description="Send and inspect local Codex agent messages")
    parser.add_argument("--root", help="Message root. Defaults to .agent-state/agents-messaging.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_send = sub.add_parser("send")
    p_send.add_argument("--sender", required=True)
    p_send.add_argument("--recipient", required=True)
    p_send.add_argument("--type", required=True)
    p_send.add_argument("--payload-file")
    p_send.add_argument("--payload-json")

    p_pending = sub.add_parser("pending")
    p_pending.add_argument("--agent-id", required=True)

    p_list = sub.add_parser("list", help="List pending, processed, and failed messages.")
    p_list.add_argument("--agent-id")
    p_list.add_argument("--status", choices=["pending", "processed", "failed"])
    p_list.add_argument("--type")
    p_list.add_argument("--sender")
    p_list.add_argument("--recipient")
    p_list.add_argument("--limit", type=int)
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Show one message record by id.")
    p_show.add_argument("message_id")
    p_show.add_argument("--json", action="store_true")

    p_thread = sub.add_parser("thread", help="Show a message and its replies.")
    p_thread.add_argument("message_id")
    p_thread.add_argument("--json", action="store_true")

    p_summary = sub.add_parser("summary", help="Summarize visible message records.")
    p_summary.add_argument("--json", action="store_true")

    p_events = sub.add_parser("events", help="Show append-only messaging events.")
    p_events.add_argument("--limit", type=int)
    p_events.add_argument("--json", action="store_true")

    p_tasks = sub.add_parser("tasks", help="Show controller task records.")
    p_tasks.add_argument("--json", action="store_true")

    p_current_error = sub.add_parser("current-error", help="Show the active operational error.")
    p_current_error.add_argument("--json", action="store_true")

    p_errors = sub.add_parser("errors", help="List current and archived operational errors.")
    p_errors.add_argument("--json", action="store_true")

    p_resolve_error = sub.add_parser("resolve-error", help="Archive the active operational error.")
    p_resolve_error.add_argument("--status", choices=["fixed", "superseded"], default="fixed")
    p_resolve_error.add_argument("--details-file")
    p_resolve_error.add_argument("--details-json")
    p_resolve_error.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    bus = MessageBus(args.root)
    logger.info("agent-msg command started", extra={"command": args.command})
    if args.command == "send":
        path = bus.send(
            AgentMessage(
                sender=args.sender,
                recipient=args.recipient,
                type=args.type,
                payload=_payload(args),
            )
        )
        print(path)
        logger.info("agent-msg send completed", extra={"path": str(path)})
        return 0
    if args.command == "pending":
        for path in bus.pending(args.agent_id):
            print(path)
        return 0
    if args.command == "list":
        records = bus.list_records(
            agent_id=args.agent_id,
            status=args.status,
            message_type=args.type,
            sender=args.sender,
            recipient=args.recipient,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps([_record_dict(record) for record in records], indent=2, sort_keys=True))
        else:
            _print_records(records)
        logger.info("agent-msg list completed", extra={"count": len(records)})
        return 0
    if args.command == "show":
        record = bus.read_record(args.message_id)
        if args.json:
            print(json.dumps(_record_dict(record), indent=2, sort_keys=True))
        else:
            _print_records([record])
            print(json.dumps(record.message.payload, indent=2, sort_keys=True))
            if record.error:
                print(f"error: {record.error}")
        return 0
    if args.command == "thread":
        records = bus.thread(args.message_id)
        if args.json:
            print(json.dumps([_record_dict(record) for record in records], indent=2, sort_keys=True))
        else:
            _print_records(records)
        return 0
    if args.command == "summary":
        summary = bus.summary()
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print(f"root: {summary['root']}")
            print(f"total: {summary['total']}")
            print(f"by_status: {summary['by_status']}")
            print(f"by_type: {summary['by_type']}")
            print(f"agents: {', '.join(summary['agents'])}")
        return 0
    if args.command == "events":
        events = bus.read_events(args.limit)
        if args.json:
            print(json.dumps(events, indent=2, sort_keys=True))
        else:
            for event in events:
                subject = event.get("message_id") or event.get("task_id") or "-"
                print(f"{event.get('event_at', '')[:22]:<22} {event.get('event', ''):<18} {subject}")
        return 0
    if args.command == "tasks":
        tasks = bus.list_task_records()
        if args.json:
            print(json.dumps(tasks, indent=2, sort_keys=True))
        else:
            print(f"{'STATUS':<24} {'UPDATED':<22} {'AGENT':<28} ID")
            for task in tasks:
                print(
                    f"{str(task.get('status', '')):<24} "
                    f"{str(task.get('updated_at', ''))[:22]:<22} "
                    f"{str(task.get('agent_id', '')):<28} "
                    f"{task.get('id', '')}"
                )
        return 0
    if args.command == "current-error":
        current = bus.read_current_error()
        if args.json:
            print(json.dumps(current, indent=2, sort_keys=True))
        elif current:
            print(f"{current.get('status')} {current.get('id')} {current.get('updated_at')}")
            print(json.dumps(current.get("error", {}), indent=2, sort_keys=True))
        else:
            print("No current error")
        return 0
    if args.command == "errors":
        errors = bus.list_error_records()
        if args.json:
            print(json.dumps(errors, indent=2, sort_keys=True))
        else:
            print(f"{'STATUS':<12} {'UPDATED':<22} {'COUNT':<7} ID")
            for error in errors:
                print(
                    f"{str(error.get('status', '')):<12} "
                    f"{str(error.get('updated_at', ''))[:22]:<22} "
                    f"{str(error.get('occurrence_count', '')):<7} "
                    f"{error.get('id', '')}"
                )
        return 0
    if args.command == "resolve-error":
        resolved = bus.resolve_current_error(status=args.status, details=_details(args))
        if args.json:
            print(json.dumps(resolved, indent=2, sort_keys=True))
        else:
            print(f"{resolved.get('status')} {resolved.get('id')}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
