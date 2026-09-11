"""Atomic file-backed persistence and querying for agent messages.

The bus owns the durable on-disk contract under `.agent-state/agents-messaging`.
It keeps inbox files, lifecycle records, task records, and an append-only event
stream together so controller UIs and agents can inspect the same facts.
"""

from __future__ import annotations

import json
import logging
import os
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .logging_config import configure_messaging_logging
from .models import AgentMessage, MessageRecord, utc_now_iso


logger = logging.getLogger(__name__)
MANIFEST_VERSION = 1


def default_message_root() -> Path:
    """Return the repository-local durable message directory by default."""
    configured = os.environ.get("AGENT_MESSAGING_ROOT")
    return Path(configured).expanduser() if configured else Path.cwd() / ".agent-state" / "agents-messaging"


class MessageBus:
    """Persist agent messages as inbox files, records, and an event log."""

    def __init__(self, root: str | Path | None = None) -> None:
        """Create a bus rooted at the configured repository-local directory."""
        configure_messaging_logging()
        self.root = Path(root).expanduser() if root else default_message_root()
        self.ensure_structure()
        logger.info("MessageBus initialized", extra={"root": str(self.root)})

    def inbox_dir(self, agent_id: str) -> Path:
        """Return the pending inbox directory for one agent."""
        return self.root / "inbox" / agent_id

    def processed_dir(self, agent_id: str) -> Path:
        """Return the processed-message archive directory for one agent."""
        return self.root / "processed" / agent_id

    def failed_dir(self, agent_id: str) -> Path:
        """Return the failed-message archive directory for one agent."""
        return self.root / "failed" / agent_id

    def records_dir(self) -> Path:
        """Return the root for durable message indexes and audit logs."""
        return self.root / "records"

    def errors_dir(self) -> Path:
        """Return the archive for tracked operational errors."""
        return self.root / "errors"

    def current_error_path(self) -> Path:
        """Return the active operational error pointer path."""
        return self.root / "current-error.json"

    def message_records_dir(self) -> Path:
        """Return the directory containing one JSON record per message."""
        return self.records_dir() / "messages"

    def task_records_dir(self) -> Path:
        """Return the directory containing controller-created task records."""
        return self.records_dir() / "tasks"

    def event_log_path(self) -> Path:
        """Return the append-only message lifecycle event log path."""
        return self.records_dir() / "events.jsonl"

    def manifest_path(self) -> Path:
        """Return the durable manifest describing the messaging tree."""
        return self.root / "manifest.json"

    def ensure_structure(self) -> None:
        """Create the transparent messaging directory structure and manifest."""
        for directory in (
            self.root / "inbox",
            self.root / "processed",
            self.root / "failed",
            self.message_records_dir(),
            self.task_records_dir(),
            self.errors_dir(),
            self.root / "debug-sessions",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.event_log_path().exists():
            self.event_log_path().write_text("", encoding="utf-8")
        manifest = {
            "version": MANIFEST_VERSION,
            "root": str(self.root),
            "purpose": "Durable transparent agent messaging, task assignment, and UI debug artifacts.",
            "directories": {
                "inbox": "Pending messages grouped by recipient agent id.",
                "processed": "Messages moved here after a handler or worker accepts them.",
                "failed": "Messages moved here with sibling .error.txt files when processing fails.",
                "records/messages": "Current lifecycle record for every known message, including payload.",
                "records/tasks": "Controller-created task records linked to task_request messages and runtime runs.",
                "current-error.json": "Current unresolved operational error alert, when one exists.",
                "errors": "Archived fixed, superseded, and historical operational error alerts.",
                "debug-sessions": "Selenium UI debugger manifests, screenshots, console logs, and network errors.",
            },
            "event_log": str(self.event_log_path()),
            "message_record_fields": [
                "id",
                "created_at",
                "updated_at",
                "sender",
                "recipient",
                "type",
                "reply_to",
                "status",
                "path",
                "folder_agent_id",
                "payload",
                "error",
            ],
            "task_statuses": ["awaiting implementation", "implementing", "complete", "need rework"],
            "error_statuses": ["active", "superseded", "fixed"],
        }
        self._write_json(self.manifest_path(), manifest)

    def send(self, message: AgentMessage) -> Path:
        """Write a message to the recipient inbox and index it."""
        inbox = self.inbox_dir(message.recipient)
        inbox.mkdir(parents=True, exist_ok=True)
        filename = f"{message.created_at.replace(':', '').replace('.', '')}-{message.id}.json"
        target = inbox / filename
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(message.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(target)
        self._write_record(MessageRecord(message=message, status="pending", path=str(target), folder_agent_id=message.recipient))
        self._append_event("sent", message, target, message.recipient)
        logger.info(
            "Message sent",
            extra={"message_id": message.id, "sender": message.sender, "recipient": message.recipient},
        )
        return target

    def pending(self, agent_id: str) -> list[Path]:
        """List pending inbox JSON files for one agent."""
        inbox = self.inbox_dir(agent_id)
        if not inbox.exists():
            return []
        paths = sorted(path for path in inbox.iterdir() if path.suffix == ".json")
        logger.info("Pending messages listed", extra={"agent_id": agent_id, "count": len(paths)})
        return paths

    def read(self, path: str | Path) -> AgentMessage:
        """Read a message file from any lifecycle folder."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return AgentMessage.from_dict(data)

    def mark_processed(self, agent_id: str, path: str | Path) -> Path:
        """Move a pending message into the processed archive."""
        source = Path(path)
        message = self.read(source)
        target_dir = self.processed_dir(agent_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        source.replace(target)
        self._write_record(MessageRecord(message=message, status="processed", path=str(target), folder_agent_id=agent_id))
        self._append_event("processed", message, target, agent_id)
        logger.info("Message marked processed", extra={"message_id": message.id, "agent_id": agent_id})
        return target

    def mark_failed(self, agent_id: str, path: str | Path, reason: str) -> Path:
        """Move a pending message into the failed archive with an error note."""
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
        logger.info("Message marked failed", extra={"message_id": message.id, "agent_id": agent_id})
        return target

    def write_task_record(self, task: Mapping[str, Any]) -> Path:
        """Persist one controller task record under records/tasks."""
        task_id = str(task.get("id") or "")
        if not task_id:
            raise ValueError("Task record requires an id")
        target = self.task_records_dir() / f"{task_id}.json"
        existing = self.read_task_record(task_id) or {}
        merged = {
            **existing,
            **dict(task),
            "updated_at": str(task.get("updated_at") or utc_now_iso()),
        }
        if "created_at" not in merged:
            merged["created_at"] = merged["updated_at"]
        self._write_json(target, merged)
        self._append_task_event(task_id, "task.updated", merged)
        logger.info("Task record written", extra={"task_id": task_id})
        return target

    def read_task_record(self, task_id: str) -> dict[str, Any] | None:
        """Load one controller task record by id."""
        path = self.task_records_dir() / f"{task_id}.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, dict) else None

    def list_task_records(self) -> list[dict[str, Any]]:
        """List all controller task records newest first."""
        tasks: list[dict[str, Any]] = []
        for path in sorted(self.task_records_dir().glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                tasks.append(value)
        tasks.sort(key=lambda task: str(task.get("updated_at") or task.get("created_at") or ""), reverse=True)
        return tasks

    def update_task_status(
        self,
        task_id: str,
        status: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> Path:
        """Update a task status and append a visible task event."""
        task = self.read_task_record(task_id) or {"id": task_id, "created_at": utc_now_iso(), "events": []}
        events = list(task.get("events") or [])
        event = {
            "ts": utc_now_iso(),
            "type": "task.status",
            "status": status,
            "message": message,
            "details": dict(details or {}),
        }
        events.append(event)
        task.update(
            {
                "status": status,
                "updated_at": event["ts"],
                "events": events[-100:],
            }
        )
        return self.write_task_record(task)

    def record_error(
        self,
        error: Mapping[str, Any],
        sender: str = "agent-error-monitor",
        recipient: str = "agent-logs-analyzer",
    ) -> dict[str, Any]:
        """Track an operational error and send the exact error object as a message."""
        error_object = dict(error)
        fingerprint = str(error_object.get("fingerprint") or error_fingerprint(error_object))
        now = utc_now_iso()
        current = self.read_current_error()
        if current and current.get("status") == "active" and current.get("fingerprint") != fingerprint:
            archived = {**current, "status": "superseded", "updated_at": now, "superseded_at": now}
            self._write_json(self.errors_dir() / f"{safe_filename(str(current.get('id') or fingerprint))}.json", archived)

        occurrence_count = 1
        history: list[dict[str, Any]] = []
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
        self._write_json(self.current_error_path(), record)
        message_path = self.send(
            AgentMessage(
                sender=sender,
                recipient=recipient,
                type="error.detected",
                payload=error_object,
            )
        )
        self._append_error_event("error.detected", record, message_path)
        logger.info("Operational error recorded", extra={"fingerprint": fingerprint, "message_path": str(message_path)})
        return record

    def read_current_error(self) -> dict[str, Any] | None:
        """Return the active operational error alert when present."""
        path = self.current_error_path()
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return dict(value) if isinstance(value, dict) else None

    def list_error_records(self) -> list[dict[str, Any]]:
        """List current and archived operational error alerts newest first."""
        records: list[dict[str, Any]] = []
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

    def resolve_current_error(
        self,
        status: str = "fixed",
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark the current operational error fixed and archive it."""
        if status not in {"fixed", "superseded"}:
            raise ValueError("resolved error status must be fixed or superseded")
        current = self.read_current_error()
        if current is None:
            raise FileNotFoundError("No current error is available to resolve")
        now = utc_now_iso()
        history = [item for item in current.get("history", []) if isinstance(item, dict)]
        history.append({"ts": now, "event": status, "details": dict(details or {})})
        archived = {
            **current,
            "status": status,
            "updated_at": now,
            "confirmed_at": now if status == "fixed" else current.get("confirmed_at"),
            "resolution": dict(details or {}),
            "history": history[-100:],
        }
        target = self.errors_dir() / f"{safe_filename(str(archived.get('id') or archived.get('fingerprint')))}.json"
        self._write_json(target, archived)
        try:
            self.current_error_path().unlink()
        except FileNotFoundError:
            pass
        self._append_error_event(f"error.{status}", archived, target)
        logger.info("Operational error resolved", extra={"status": status, "path": str(target)})
        return archived

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
        """List current message lifecycle records with optional filters."""
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
        logger.info("Message records listed", extra={"count": len(values)})
        return values

    def read_record(self, message_id: str) -> MessageRecord:
        """Read one current message lifecycle record by message id."""
        records = self.list_records()
        for record in records:
            if record.message.id == message_id:
                return record
        raise FileNotFoundError(f"message not found: {message_id}")

    def thread(self, message_id: str) -> list[MessageRecord]:
        """Return a message and all replies linked through reply_to."""
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
        """Summarize visible messages, tasks, and the messaging root."""
        records = self.list_records()
        tasks = self.list_task_records()
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        task_statuses: dict[str, int] = {}
        agents: set[str] = set()
        for record in records:
            by_status[record.status] = by_status.get(record.status, 0) + 1
            by_type[record.message.type] = by_type.get(record.message.type, 0) + 1
            agents.add(record.message.sender)
            agents.add(record.message.recipient)
        for task in tasks:
            status = str(task.get("status") or "unknown")
            task_statuses[status] = task_statuses.get(status, 0) + 1
        error_records = self.list_error_records()
        active_errors = sum(1 for error in error_records if error.get("status") == "active")
        return {
            "root": str(self.root),
            "manifest": str(self.manifest_path()),
            "event_log": str(self.event_log_path()),
            "total": len(records),
            "tasks": len(tasks),
            "by_status": by_status,
            "by_type": by_type,
            "task_statuses": task_statuses,
            "active_errors": active_errors,
            "current_error": self.read_current_error(),
            "agents": sorted(agent for agent in agents if agent),
        }

    def read_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Read append-only messaging events newest first."""
        path = self.event_log_path()
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
        events.reverse()
        if limit is not None:
            return events[: max(limit, 0)]
        return events

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
            "payload": message.payload,
        }
        if error:
            data["error"] = error
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    def _append_task_event(self, task_id: str, event: str, task: Mapping[str, Any]) -> None:
        events = self.event_log_path()
        events.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "event": event,
            "event_at": utc_now_iso(),
            "task_id": task_id,
            "status": task.get("status"),
            "agent_id": task.get("agent_id"),
            "message_id": task.get("message_id"),
            "run_id": task.get("run_id"),
            "session_id": task.get("session_id"),
        }
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    def _append_error_event(self, event: str, error: Mapping[str, Any], path: Path) -> None:
        events = self.event_log_path()
        events.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "event": event,
            "event_at": utc_now_iso(),
            "error_id": error.get("id"),
            "fingerprint": error.get("fingerprint"),
            "status": error.get("status"),
            "status_path": str(path),
            "message_type": "error.detected" if event == "error.detected" else "error.status",
            "agent_id": "agent-logs-analyzer",
        }
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(dict(value), indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

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


def safe_filename(value: str) -> str:
    """Return a conservative filename stem for an error record."""
    cleaned = "".join(character if character.isalnum() or character in "-_." else "-" for character in value)
    return cleaned.strip(".-")[:120] or "error"


def error_fingerprint(error: Mapping[str, Any]) -> str:
    """Build a stable fingerprint from an exact error object."""
    text = json.dumps(dict(error), sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
