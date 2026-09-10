"""Durable runtime events and session/run storage."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


EVENT_TYPES = frozenset(
    {
        "run.started",
        "run.completed",
        "run.failed",
        "run.cancelled",
        "resolver.completed",
        "workflow.started",
        "workflow.completed",
        "workflow.step.queued",
        "workflow.step.started",
        "workflow.step.progress",
        "workflow.step.completed",
        "workflow.step.failed",
        "agent.started",
        "agent.message.delta",
        "agent.message.completed",
        "agent.usage.updated",
        "agent.completed",
        "tool.started",
        "tool.progress",
        "tool.completed",
        "tool.failed",
        "artifact.created",
        "file.changed",
        "background.started",
        "background.progress",
        "background.completed",
        "background.failed",
        "error",
    }
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def utc_now() -> str:
    """Return the current UTC time in ISO 8601 form."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """One immutable runtime fact shared by persistence and subscribers.

    A sequence value of zero asks :class:`EventHub` to assign the next value.
    Callers may supply a positive value only when it is exactly the next value.
    """

    seq: int
    type: str
    ts: str
    run_id: str
    session_id: str
    agent_id: str | None = None
    step_id: str | None = None
    status: str | None = None
    message: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "type": self.type,
            "ts": self.ts,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "step_id": self.step_id,
            "status": self.status,
            "message": self.message,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeEvent":
        return cls(
            seq=int(value["seq"]),
            type=str(value["type"]),
            ts=str(value["ts"]),
            run_id=str(value["run_id"]),
            session_id=str(value["session_id"]),
            agent_id=value.get("agent_id"),
            step_id=value.get("step_id"),
            status=value.get("status"),
            message=value.get("message"),
            payload=dict(value.get("payload") or {}),
        )


class EventHub:
    """Append events durably and fan the same objects out to live subscribers."""

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root).resolve()
        for directory in ("plans", "sessions", "logs", "cache"):
            (self.state_root / directory).mkdir(parents=True, exist_ok=True)
        self.logs_root = self.state_root / "logs"
        self.sessions_root = self.state_root / "sessions"
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._next_seq: dict[tuple[str, str], int] = {}
        self._subscribers: dict[
            asyncio.Queue[RuntimeEvent], tuple[str | None, str | None]
        ] = {}

    @staticmethod
    def new_event(
        event_type: str,
        *,
        run_id: str,
        session_id: str,
        **values: Any,
    ) -> RuntimeEvent:
        """Create an unsequenced event ready for :meth:`emit`."""
        return RuntimeEvent(
            seq=0,
            type=event_type,
            ts=values.pop("ts", None) or utc_now(),
            run_id=run_id,
            session_id=session_id,
            **values,
        )

    async def emit(self, event: RuntimeEvent) -> RuntimeEvent:
        """Persist, flush, and publish one event in per-run sequence order."""
        self._validate_event(event)
        key = (event.session_id, event.run_id)
        async with self._locks.setdefault(key, asyncio.Lock()):
            next_seq = self._next_seq.get(key)
            if next_seq is None:
                existing = self.load_run(event.run_id, event.session_id)
                next_seq = existing[-1].seq + 1 if existing else 1
            if event.seq not in (0, next_seq):
                raise ValueError(
                    f"Event sequence {event.seq} is invalid for run {event.run_id!r}; "
                    f"expected {next_seq}."
                )
            emitted = replace(event, seq=next_seq)
            self._append(emitted)
            self._next_seq[key] = next_seq + 1
            for queue, (run_filter, session_filter) in tuple(self._subscribers.items()):
                if (run_filter is None or run_filter == emitted.run_id) and (
                    session_filter is None or session_filter == emitted.session_id
                ):
                    await queue.put(emitted)
            return emitted

    def subscribe(
        self,
        run_id: str | None = None,
        *,
        session_id: str | None = None,
        maxsize: int = 0,
    ) -> asyncio.Queue[RuntimeEvent]:
        """Subscribe to future events matching the optional run filters."""
        if run_id is not None:
            self._safe_id(run_id, "run_id")
        if session_id is not None:
            self._safe_id(session_id, "session_id")
        queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[queue] = (run_id, session_id)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RuntimeEvent]) -> None:
        """Remove a previously registered event subscription."""
        self._subscribers.pop(queue, None)

    def run_dir(self, session_id: str, run_id: str, *, create: bool = False) -> Path:
        session_id = self._safe_id(session_id, "session_id")
        run_id = self._safe_id(run_id, "run_id")
        path = self._contained(self.logs_root / session_id / run_id)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def session_dir(self, session_id: str, *, create: bool = False) -> Path:
        session_id = self._safe_id(session_id, "session_id")
        path = self._contained(self.sessions_root / session_id)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def load_run(self, run_id: str, session_id: str | None = None) -> list[RuntimeEvent]:
        """Reload a run's persisted events.

        Supplying ``session_id`` is preferred. A run-only lookup succeeds when
        exactly one session contains that run ID.
        """
        run_id = self._safe_id(run_id, "run_id")
        if session_id is None:
            candidates = list(self.logs_root.glob(f"*/{run_id}/events.jsonl"))
            if len(candidates) > 1:
                raise ValueError(f"Run ID {run_id!r} exists in multiple sessions.")
            event_path = self._contained(candidates[0]) if candidates else None
        else:
            event_path = self.run_dir(session_id, run_id) / "events.jsonl"
        if event_path is None or not event_path.is_file():
            return []
        events: list[RuntimeEvent] = []
        with event_path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
            for line_number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    events.append(RuntimeEvent.from_dict(json.loads(line)))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    # A process/filesystem crash can leave only the last append torn.
                    if line_number == len(lines) and not line.endswith("\n"):
                        break
                    raise ValueError(
                        f"Invalid event at {event_path}:{line_number}: {exc}"
                    ) from exc
        return events

    def write_session(self, session_id: str, metadata: Mapping[str, Any]) -> Path:
        path = self.session_dir(session_id, create=True) / "session.json"
        self._write_json(path, {**metadata, "session_id": session_id})
        return path

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        path = self.session_dir(session_id) / "session.json"
        return self._read_json(path)

    def write_run_metadata(
        self, session_id: str, run_id: str, metadata: Mapping[str, Any]
    ) -> Path:
        path = self.run_dir(session_id, run_id, create=True) / "run.json"
        self._write_json(
            path, {**metadata, "session_id": session_id, "run_id": run_id}
        )
        return path

    def load_run_metadata(self, session_id: str, run_id: str) -> dict[str, Any] | None:
        return self._read_json(self.run_dir(session_id, run_id) / "run.json")

    def _append(self, event: RuntimeEvent) -> None:
        path = self.run_dir(event.session_id, event.run_id, create=True) / "events.jsonl"
        encoded = json.dumps(event.to_dict(), separators=(",", ":"), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _validate_event(self, event: RuntimeEvent) -> None:
        self._safe_id(event.run_id, "run_id")
        self._safe_id(event.session_id, "session_id")
        if event.type not in EVENT_TYPES:
            raise ValueError(f"Unsupported runtime event type: {event.type!r}")
        if event.seq < 0:
            raise ValueError("Event sequence cannot be negative.")
        try:
            json.dumps(event.to_dict())
        except (TypeError, ValueError) as exc:
            raise ValueError("Runtime event must be JSON serializable.") from exc

    @staticmethod
    def _safe_id(value: str, label: str) -> str:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError(f"Unsafe {label}: {value!r}")
        return value

    def _contained(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.state_root and self.state_root not in resolved.parents:
            raise ValueError(f"State path escapes the configured root: {path}")
        return resolved

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"Expected a JSON object in {path}.")
        return value


def terminal_event(events: Iterable[RuntimeEvent]) -> RuntimeEvent | None:
    """Return the latest terminal event, if the stream contains one."""
    terminal_types = {"run.completed", "run.failed", "run.cancelled"}
    return next((event for event in reversed(list(events)) if event.type in terminal_types), None)
