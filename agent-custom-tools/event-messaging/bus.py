"""
Stores compact file-backed agent messages and lifecycle events.

This is the direct-folder version of the monorepo internal messaging bus: inbox
files, processed/failed archives, message indexes, task records, and current
operational errors all live below one transparent state root.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from models import AgentMessage, MessageRecord, utc_now_iso


MANIFEST_VERSION = 1


def default_message_root() -> Path:
    """Return the default repository-local message root."""
    configured = os.environ.get("AGENT_MESSAGING_ROOT")
    return Path(configured).expanduser() if configured else Path.cwd() / ".agent-state" / "agents-messaging"


def safe_filename(value: str) -> str:
    """Return a conservative filename stem."""
    cleaned = "".join(character if character.isalnum() or character in "-_." else "-" for character in value)
    return cleaned.strip(".-")[:120] or "record"


def error_fingerprint(error: Mapping[str, Any]) -> str:
    """Build a stable short fingerprint from an error object."""
    text = json.dumps(dict(error), sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class MessageBus:
    """Persist agent messages and related task/error records."""

    def __init__(self, root: str | Path | None = None) -> None:
        """Create a message bus rooted at the supplied or default state path."""
        self.root = Path(root).expanduser() if root else default_message_root()
        self.ensure_structure()

    def inbox_dir(self, agent_id: str) -> Path:
        """Return the pending inbox directory for one agent."""
        return self.root / "inbox" / agent_id

    def processed_dir(self, agent_id: str) -> Path:
        """Return the processed-message archive for one agent."""
        return self.root / "processed" / agent_id

    def failed_dir(self, agent_id: str) -> Path:
        """Return the failed-message archive for one agent."""
        return self.root / "failed" / agent_id

    def records_dir(self) -> Path:
        """Return the durable record directory."""
        return self.root / "records"

    def message_records_dir(self) -> Path:
        """Return the per-message record directory."""
        return self.records_dir() / "messages"

    def task_records_dir(self) -> Path:
        """Return the task record directory."""
        return self.records_dir() / "tasks"

    def errors_dir(self) -> Path:
        """Return the archived error record directory."""
        return self.root / "errors"

    def event_log_path(self) -> Path:
        """Return the append-only event log path."""
        return self.records_dir() / "events.jsonl"

    def manifest_path(self) -> Path:
        """Return the manifest path."""
        return self.root / "manifest.json"

    def current_error_path(self) -> Path:
        """Return the active operational error path."""
        return self.root / "current-error.json"

    def ensure_structure(self) -> None:
        """Create the durable message directory structure."""
        for directory in (
            self.root / "inbox",
            self.root / "processed",
            self.root / "failed",
            self.message_records_dir(),
            self.task_records_dir(),
            self.errors_dir(),
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.event_log_path().exists():
            self.event_log_path().write_text("", encoding="utf-8")
        self.write_json(
            self.manifest_path(),
            {
                "version": MANIFEST_VERSION,
                "root": str(self.root),
                "purpose": "Compact local agent message bus.",
                "directories": ["inbox", "processed", "failed", "records/messages", "records/tasks", "errors"],
            },
        )

    def send(self, message: AgentMessage) -> Path:
        """Write a message to the recipient inbox and index it."""
        target_dir = self.inbox_dir(message.recipient)
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f"{message.created_at.replace(':', '').replace('.', '')}-{message.id}.json"
        target = target_dir / name
        self.write_json(target, message.to_dict())
        self.write_record(MessageRecord(message, "pending", str(target), message.recipient))
        self.append_event("sent", message, target, message.recipient)
        return target

    def pending(self, agent_id: str) -> list[Path]:
        """List pending message files for one agent."""
        inbox = self.inbox_dir(agent_id)
        if not inbox.exists():
            return []
        return sorted(path for path in inbox.iterdir() if path.suffix == ".json")

    def read(self, path: str | Path) -> AgentMessage:
        """Read a message file from any lifecycle folder."""
        return AgentMessage.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def mark_processed(self, agent_id: str, path: str | Path) -> Path:
        """Move a message to processed and update its record."""
        source = Path(path)
        message = self.read(source)
        target = self.processed_dir(agent_id) / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        self.write_record(MessageRecord(message, "processed", str(target), agent_id))
        self.append_event("processed", message, target, agent_id)
        return target

    def mark_failed(self, agent_id: str, path: str | Path, reason: str) -> Path:
        """Move a message to failed, write the reason, and update its record."""
        source = Path(path)
        message = self.read(source)
        target = self.failed_dir(agent_id) / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        target.with_suffix(".error.txt").write_text(reason, encoding="utf-8")
        self.write_record(MessageRecord(message, "failed", str(target), agent_id, error=reason))
        self.append_event("failed", message, target, agent_id, reason)
        return target

    def write_task_record(self, task: Mapping[str, Any]) -> Path:
        """Persist or update one task record."""
        task_id = str(task.get("id") or "")
        if not task_id:
            raise ValueError("Task record requires an id")
        existing = self.read_task_record(task_id) or {}
        merged = {**existing, **dict(task), "updated_at": str(task.get("updated_at") or utc_now_iso())}
        merged.setdefault("created_at", merged["updated_at"])
        target = self.task_records_dir() / f"{task_id}.json"
        self.write_json(target, merged)
        self.append_task_event(task_id, merged)
        return target

    def read_task_record(self, task_id: str) -> dict | None:
        """Load one task record by id."""
        path = self.task_records_dir() / f"{task_id}.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, dict) else None

    def list_task_records(self) -> list[dict]:
        """List task records newest first."""
        records = []
        for path in sorted(self.task_records_dir().glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
        records.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return records

    def update_task_status(self, task_id: str, status: str, message: str, details: Mapping[str, Any] | None = None) -> Path:
        """Append a status event to one task record."""
        task = self.read_task_record(task_id) or {"id": task_id, "created_at": utc_now_iso(), "events": []}
        events = list(task.get("events") or [])
        event = {"ts": utc_now_iso(), "type": "task.status", "status": status, "message": message, "details": dict(details or {})}
        events.append(event)
        task.update({"status": status, "updated_at": event["ts"], "events": events[-100:]})
        return self.write_task_record(task)

    def record_error(self, error: Mapping[str, Any], sender: str = "agent-error-monitor", recipient: str = "agent-logs-analyzer") -> dict:
        """Track an operational error and send it as a durable message."""
        error_object = dict(error)
        fingerprint = str(error_object.get("fingerprint") or error_fingerprint(error_object))
        now = utc_now_iso()
        current = self.read_current_error()
        if current and current.get("status") == "active" and current.get("fingerprint") != fingerprint:
            archived = {**current, "status": "superseded", "updated_at": now, "superseded_at": now}
            self.write_json(self.errors_dir() / f"{safe_filename(str(current.get('id') or fingerprint))}.json", archived)
        occurrence_count = 1
        history = []
        if current and current.get("fingerprint") == fingerprint:
            occurrence_count = int(current.get("occurrence_count") or 0) + 1
            history = [item for item in current.get("history", []) if isinstance(item, dict)]
        history.append({"ts": now, "event": "detected"})
        record = {
            "id": f"error-{fingerprint}",
            "status": "active",
            "fingerprint": fingerprint,
            "created_at": str(current.get("created_at") if current and current.get("fingerprint") == fingerprint else now),
            "updated_at": now,
            "occurrence_count": occurrence_count,
            "error": error_object,
            "history": history[-100:],
        }
        self.write_json(self.current_error_path(), record)
        message_path = self.send(AgentMessage(sender=sender, recipient=recipient, type="error.detected", payload=error_object))
        self.append_error_event("error.detected", record, message_path)
        return record

    def read_current_error(self) -> dict | None:
        """Return the active operational error when present."""
        path = self.current_error_path()
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return dict(value) if isinstance(value, dict) else None

    def resolve_current_error(self, status: str = "fixed", details: Mapping[str, Any] | None = None) -> dict:
        """Archive the active operational error as fixed or superseded."""
        if status not in {"fixed", "superseded"}:
            raise ValueError("resolved error status must be fixed or superseded")
        current = self.read_current_error()
        if current is None:
            raise FileNotFoundError("No current error is available to resolve")
        now = utc_now_iso()
        history = [item for item in current.get("history", []) if isinstance(item, dict)]
        history.append({"ts": now, "event": status, "details": dict(details or {})})
        archived = {**current, "status": status, "updated_at": now, "resolution": dict(details or {}), "history": history[-100:]}
        target = self.errors_dir() / f"{safe_filename(str(archived.get('id') or archived.get('fingerprint')))}.json"
        self.write_json(target, archived)
        self.current_error_path().unlink(missing_ok=True)
        self.append_error_event(f"error.{status}", archived, target)
        return archived

    def list_error_records(self) -> list[dict]:
        """List current and archived errors newest first."""
        records = []
        current = self.read_current_error()
        if current:
            records.append(current)
        for path in sorted(self.errors_dir().glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
        records.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return records

    def list_records(self, agent_id: str | None = None, status: str | None = None, message_type: str | None = None, limit: int | None = None) -> list[MessageRecord]:
        """List visible message lifecycle records."""
        records = self.indexed_records()
        for scanned in self.scan_folder_records():
            records.setdefault(scanned.message.id, scanned)
        values = list(records.values())
        if agent_id:
            values = [record for record in values if agent_id in {record.folder_agent_id, record.message.sender, record.message.recipient}]
        if status:
            values = [record for record in values if record.status == status]
        if message_type:
            values = [record for record in values if record.message.type == message_type]
        values.sort(key=lambda record: (record.message.created_at, record.message.id), reverse=True)
        return values[: max(limit, 0)] if limit is not None else values

    def read_record(self, message_id: str) -> MessageRecord:
        """Read one message record by id."""
        for record in self.list_records():
            if record.message.id == message_id:
                return record
        raise FileNotFoundError(f"message not found: {message_id}")

    def thread(self, message_id: str) -> list[MessageRecord]:
        """Return one message and all linked replies."""
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
        result = [records[record_id] for record_id in thread_ids]
        result.sort(key=lambda record: (record.message.created_at, record.message.id))
        return result

    def summary(self) -> dict:
        """Summarize current messages, tasks, agents, and errors."""
        records = self.list_records()
        tasks = self.list_task_records()
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        task_statuses: dict[str, int] = {}
        agents: set[str] = set()
        for record in records:
            by_status[record.status] = by_status.get(record.status, 0) + 1
            by_type[record.message.type] = by_type.get(record.message.type, 0) + 1
            agents.update([record.message.sender, record.message.recipient])
        for task in tasks:
            status = str(task.get("status") or "unknown")
            task_statuses[status] = task_statuses.get(status, 0) + 1
        return {
            "root": str(self.root),
            "total": len(records),
            "tasks": len(tasks),
            "by_status": by_status,
            "by_type": by_type,
            "task_statuses": task_statuses,
            "active_errors": sum(1 for item in self.list_error_records() if item.get("status") == "active"),
            "agents": sorted(agent for agent in agents if agent),
        }

    def read_events(self, limit: int | None = None) -> list[dict]:
        """Read append-only events newest first."""
        events = []
        if not self.event_log_path().is_file():
            return events
        for line in self.event_log_path().read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
        events.reverse()
        return events[: max(limit, 0)] if limit is not None else events

    def write_record(self, record: MessageRecord) -> None:
        """Write one message lifecycle record."""
        self.write_json(self.message_records_dir() / f"{record.message.id}.json", record.to_dict())

    def append_event(self, event: str, message: AgentMessage, path: Path, folder_agent_id: str, error: str | None = None) -> None:
        """Append one message lifecycle event."""
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
            "payload": message.payload,
        }
        if error:
            data["error"] = error
        with self.event_log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    def append_task_event(self, task_id: str, task: Mapping[str, Any]) -> None:
        """Append one task update event."""
        data = {
            "event": "task.updated",
            "event_at": utc_now_iso(),
            "task_id": task_id,
            "status": task.get("status"),
            "agent_id": task.get("agent_id"),
            "message_id": task.get("message_id"),
            "run_id": task.get("run_id"),
        }
        with self.event_log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    def append_error_event(self, event: str, error: Mapping[str, Any], path: Path) -> None:
        """Append one operational error event."""
        data = {
            "event": event,
            "event_at": utc_now_iso(),
            "error_id": error.get("id"),
            "fingerprint": error.get("fingerprint"),
            "status": error.get("status"),
            "status_path": str(path),
        }
        with self.event_log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    def write_json(self, path: Path, value: Mapping[str, Any]) -> None:
        """Atomically write one JSON mapping."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def indexed_records(self) -> dict[str, MessageRecord]:
        """Load indexed lifecycle records."""
        records = {}
        for path in sorted(self.message_records_dir().glob("*.json")):
            try:
                record = MessageRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            records[record.message.id] = record
        return records

    def scan_folder_records(self) -> list[MessageRecord]:
        """Recover lifecycle records by scanning message folders."""
        records = []
        for status, folder in (("pending", "inbox"), ("processed", "processed"), ("failed", "failed")):
            base = self.root / folder
            if not base.exists():
                continue
            for agent_dir in sorted(path for path in base.iterdir() if path.is_dir()):
                for path in sorted(agent_dir.glob("*.json")):
                    try:
                        message = self.read(path)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
                    error = path.with_suffix(".error.txt").read_text(encoding="utf-8") if status == "failed" and path.with_suffix(".error.txt").exists() else None
                    records.append(MessageRecord(message, status, str(path), agent_dir.name, error=error))
        return records
