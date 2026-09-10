"""Atomic file-backed persistence and querying for agent messages."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from .models import AgentMessage, MessageRecord, utc_now_iso


def default_message_root() -> Path:
    """Return the repository-local durable message directory by default."""
    configured = os.environ.get("AGENT_MESSAGING_ROOT")
    return Path(configured).expanduser() if configured else Path.cwd() / ".agent-state" / "agents-messaging"


class MessageBus:
    """Persist agent messages as inbox files, records, and an event log."""

    def __init__(self, root: str | Path | None = None) -> None:
        """Create a bus rooted at the configured repository-local directory."""
        self.root = Path(root).expanduser() if root else default_message_root()

    def inbox_dir(self, agent_id: str) -> Path:
        return self.root / "inbox" / agent_id

    def processed_dir(self, agent_id: str) -> Path:
        return self.root / "processed" / agent_id

    def failed_dir(self, agent_id: str) -> Path:
        return self.root / "failed" / agent_id

    def records_dir(self) -> Path:
        return self.root / "records"

    def message_records_dir(self) -> Path:
        return self.records_dir() / "messages"

    def event_log_path(self) -> Path:
        return self.records_dir() / "events.jsonl"

    def send(self, message: AgentMessage) -> Path:
        inbox = self.inbox_dir(message.recipient)
        inbox.mkdir(parents=True, exist_ok=True)
        filename = f"{message.created_at.replace(':', '').replace('.', '')}-{message.id}.json"
        target = inbox / filename
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(message.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(target)
        self._write_record(MessageRecord(message=message, status="pending", path=str(target), folder_agent_id=message.recipient))
        self._append_event("sent", message, target, message.recipient)
        return target

    def pending(self, agent_id: str) -> list[Path]:
        inbox = self.inbox_dir(agent_id)
        if not inbox.exists():
            return []
        return sorted(path for path in inbox.iterdir() if path.suffix == ".json")

    def read(self, path: str | Path) -> AgentMessage:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return AgentMessage.from_dict(data)

    def mark_processed(self, agent_id: str, path: str | Path) -> Path:
        source = Path(path)
        message = self.read(source)
        target_dir = self.processed_dir(agent_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        source.replace(target)
        self._write_record(MessageRecord(message=message, status="processed", path=str(target), folder_agent_id=agent_id))
        self._append_event("processed", message, target, agent_id)
        return target

    def mark_failed(self, agent_id: str, path: str | Path, reason: str) -> Path:
        source = Path(path)
        message = self.read(source)
        target_dir = self.failed_dir(agent_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        source.replace(target)
        reason_path = target.with_suffix(".error.txt")
        reason_path.write_text(reason, encoding="utf-8")
        self._write_record(
            MessageRecord(message=message, status="failed", path=str(target), folder_agent_id=agent_id, error=reason)
        )
        self._append_event("failed", message, target, agent_id, error=reason)
        return target

    def list_records(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        message_type: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        records = self._indexed_records()
        for scanned in self._scan_folder_records():
            records.setdefault(scanned.message.id, scanned)

        values = list(records.values())
        if agent_id:
            values = [
                record
                for record in values
                if record.folder_agent_id == agent_id
                or record.message.sender == agent_id
                or record.message.recipient == agent_id
            ]
        if status:
            values = [record for record in values if record.status == status]
        if message_type:
            values = [record for record in values if record.message.type == message_type]
        if sender:
            values = [record for record in values if record.message.sender == sender]
        if recipient:
            values = [record for record in values if record.message.recipient == recipient]

        values.sort(key=lambda record: (record.message.created_at, record.message.id), reverse=True)
        if limit is not None:
            values = values[: max(limit, 0)]
        return values

    def read_record(self, message_id: str) -> MessageRecord:
        records = self.list_records()
        for record in records:
            if record.message.id == message_id:
                return record
        raise FileNotFoundError(f"message not found: {message_id}")

    def thread(self, message_id: str) -> list[MessageRecord]:
        records = {record.message.id: record for record in self.list_records()}
        if message_id not in records:
            raise FileNotFoundError(f"message not found: {message_id}")

        root_id = message_id
        while records[root_id].message.reply_to and records[root_id].message.reply_to in records:
            root_id = records[root_id].message.reply_to or root_id

        thread_ids = {root_id}
        changed = True
        while changed:
            changed = False
            for record_id, record in records.items():
                if record.message.reply_to in thread_ids and record_id not in thread_ids:
                    thread_ids.add(record_id)
                    changed = True

        thread = [records[record_id] for record_id in thread_ids]
        thread.sort(key=lambda record: (record.message.created_at, record.message.id))
        return thread

    def summary(self) -> dict[str, object]:
        records = self.list_records()
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        agents: set[str] = set()
        for record in records:
            by_status[record.status] = by_status.get(record.status, 0) + 1
            by_type[record.message.type] = by_type.get(record.message.type, 0) + 1
            agents.add(record.message.sender)
            agents.add(record.message.recipient)
        return {
            "root": str(self.root),
            "total": len(records),
            "by_status": by_status,
            "by_type": by_type,
            "agents": sorted(agent for agent in agents if agent),
        }

    def _write_record(self, record: MessageRecord) -> None:
        directory = self.message_records_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{record.message.id}.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(target)

    def _append_event(
        self,
        event: str,
        message: AgentMessage,
        path: Path,
        folder_agent_id: str,
        *,
        error: str | None = None,
    ) -> None:
        events = self.event_log_path()
        events.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "event": event,
            "event_at": utc_now_iso(),
            "message_id": message.id,
            "message_type": message.type,
            "sender": message.sender,
            "recipient": message.recipient,
            "reply_to": message.reply_to,
            "status_path": str(path),
            "folder_agent_id": folder_agent_id,
        }
        if error:
            data["error"] = error
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    def _indexed_records(self) -> dict[str, MessageRecord]:
        directory = self.message_records_dir()
        if not directory.exists():
            return {}
        records: dict[str, MessageRecord] = {}
        for path in sorted(directory.glob("*.json")):
            try:
                record = MessageRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            records[record.message.id] = record
        return records

    def _scan_folder_records(self) -> Iterable[MessageRecord]:
        for status in ("pending", "processed", "failed"):
            base = self.root / ("inbox" if status == "pending" else status)
            if not base.exists():
                continue
            for agent_dir in sorted(path for path in base.iterdir() if path.is_dir()):
                for path in sorted(agent_dir.glob("*.json")):
                    try:
                        message = self.read(path)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
                    error = None
                    if status == "failed":
                        error_path = path.with_suffix(".error.txt")
                        if error_path.exists():
                            error = error_path.read_text(encoding="utf-8")
                    yield MessageRecord(
                        message=message,
                        status=status,
                        path=str(path),
                        folder_agent_id=agent_dir.name,
                        error=error,
                    )
