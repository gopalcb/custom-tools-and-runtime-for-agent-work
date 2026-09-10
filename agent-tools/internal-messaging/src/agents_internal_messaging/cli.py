"""Command-line interface for sending and inspecting agent messages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import shorten

from .bus import MessageBus
from .models import AgentMessage, MessageRecord


def _payload(args: argparse.Namespace) -> dict:
    if args.payload_file:
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if args.payload_json:
        return json.loads(args.payload_json)
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

    args = parser.parse_args(argv)
    bus = MessageBus(args.root)
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
