"""Derive final run artifacts exclusively from the persisted event stream."""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .events import EventHub, RuntimeEvent, terminal_event
from .memory.service import MemoryService


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompletionArtifacts:
    run: Path
    summary: Path
    metrics: Path
    artifacts: Path
    memory_candidates: Path


def finalize_run(
    event_hub: EventHub,
    memory_service: MemoryService,
    session_id: str,
    run_id: str,
) -> CompletionArtifacts:
    """Read persisted events once and derive every completion artifact."""
    events = event_hub.load_run(run_id, session_id)
    if not events:
        raise ValueError(f"Cannot finalize run {run_id!r}: no persisted events.")
    logger.info(
        "Finalizing run artifacts",
        extra={"run_id": run_id, "session_id": session_id, "event_count": len(events)},
    )
    run_dir = event_hub.run_dir(session_id, run_id, create=True)
    run_data = _run_metadata(events)
    metrics = _metrics(events)
    artifacts = _artifact_index(events)
    candidates = memory_service.prepare_candidates(events)

    paths = CompletionArtifacts(
        run=run_dir / "run.json",
        summary=run_dir / "summary.md",
        metrics=run_dir / "metrics.json",
        artifacts=run_dir / "artifacts.json",
        memory_candidates=run_dir / "memory_candidates.json",
    )
    _write_json(paths.run, run_data)
    _write_text(paths.summary, _summary(events, run_data, metrics, artifacts))
    _write_json(paths.metrics, metrics)
    _write_json(paths.artifacts, artifacts)
    _write_json(paths.memory_candidates, candidates)
    logger.info(
        "Run artifacts finalized",
        extra={"run_id": run_id, "session_id": session_id, "run_dir": str(run_dir)},
    )
    return paths


async def post_completion(
    run: Any,
    *,
    event_hub: EventHub | None = None,
    memory_service: MemoryService | None = None,
) -> CompletionArtifacts:
    """Finalize a runtime context without collecting a second event stream.

    ``run`` supplies ``session_id`` and ``run_id``. The services may be passed
    explicitly or exposed as ``event_hub``/``events`` and ``memory`` attributes.
    """
    hub = event_hub or getattr(run, "event_hub", None) or getattr(run, "events", None)
    memory = memory_service or getattr(run, "memory_service", None) or getattr(run, "memory", None)
    if not isinstance(hub, EventHub):
        raise TypeError("post_completion requires an EventHub.")
    if not isinstance(memory, MemoryService):
        raise TypeError("post_completion requires a MemoryService.")
    return finalize_run(hub, memory, run.session_id, run.run_id)


def _run_metadata(events: list[RuntimeEvent]) -> dict[str, Any]:
    first = events[0]
    terminal = terminal_event(events)
    started = next((event for event in events if event.type == "run.started"), first)
    finished = terminal or events[-1]
    status = {
        "run.completed": "completed",
        "run.failed": "failed",
        "run.cancelled": "cancelled",
    }.get(finished.type, "running")
    return {
        "run_id": first.run_id,
        "session_id": first.session_id,
        "status": status,
        "started_at": started.ts,
        "finished_at": finished.ts if terminal else None,
        "duration_seconds": _duration(started.ts, finished.ts) if terminal else None,
        "event_count": len(events),
        "last_seq": events[-1].seq,
        "agent_ids": sorted({event.agent_id for event in events if event.agent_id}),
    }


def _metrics(events: list[RuntimeEvent]) -> dict[str, Any]:
    by_type: dict[str, int] = defaultdict(int)
    for event in events:
        by_type[event.type] += 1
    attempts: dict[str, int] = defaultdict(int)
    for event in events:
        if event.type == "workflow.step.started" and event.step_id:
            attempts[event.step_id] += 1
    retry_count = sum(max(0, count - 1) for count in attempts.values())
    retry_count += sum(
        1
        for event in events
        if event.payload.get("retry") is True and event.type != "workflow.step.started"
    )
    validation_events = [
        event
        for event in events
        if event.payload.get("validation") is not None
        or (event.step_id and "validat" in event.step_id.lower())
    ]
    background = [event for event in events if event.type == "background.started"]
    changed_paths = sorted(
        {
            str(event.payload["path"])
            for event in events
            if event.type == "file.changed" and event.payload.get("path")
        }
    )
    return {
        "run_duration_seconds": _run_duration(events),
        "step_durations_seconds": _paired_durations(events, "workflow.step", "step_id"),
        "agent_durations_seconds": _paired_durations(events, "agent", "agent_id"),
        "tool_durations_seconds": _paired_durations(events, "tool", "tool"),
        "background_durations_seconds": _paired_durations(events, "background", "task_id"),
        "retries": retry_count,
        "tools": {
            "calls": by_type["tool.started"],
            "completed": by_type["tool.completed"],
            "failed": by_type["tool.failed"],
        },
        "validation": {
            "events": len(validation_events),
            "failed": sum(event.type.endswith(".failed") for event in validation_events),
            "status": _validation_status(validation_events),
        },
        "file_changes": {"count": len(changed_paths), "paths": changed_paths},
        "background_tasks": {
            "count": len(background),
            "completed": by_type["background.completed"],
            "failed": by_type["background.failed"],
        },
        "events_by_type": dict(sorted(by_type.items())),
    }


def _artifact_index(events: Iterable[RuntimeEvent]) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        if event.type != "artifact.created" or not event.payload.get("path"):
            continue
        path = str(event.payload["path"])
        kind = str(event.payload.get("kind", "file"))
        key = (path, kind)
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(
            {
                "path": path,
                "kind": kind,
                "created_at": event.ts,
                "seq": event.seq,
                **{
                    key: value
                    for key, value in event.payload.items()
                    if key not in {"path", "kind", "created_at", "seq"}
                },
            }
        )
    return {"artifacts": artifacts}


def _summary(
    events: list[RuntimeEvent],
    run: Mapping[str, Any],
    metrics: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> str:
    terminal = terminal_event(events)
    final_message = next(
        (event.message for event in reversed(events) if event.message), None
    )
    lines = [
        f"# Run {run['run_id']}",
        "",
        f"- Status: {run['status']}",
        f"- Started: {run['started_at']}",
        f"- Finished: {run['finished_at'] or 'in progress'}",
        f"- Events: {run['event_count']}",
        f"- Tool calls: {metrics['tools']['calls']}",
        f"- Files changed: {metrics['file_changes']['count']}",
        f"- Artifacts: {len(artifacts['artifacts'])}",
    ]
    if final_message:
        lines.extend(["", "## Result", "", final_message])
    elif terminal and terminal.type != "run.completed":
        lines.extend(["", "## Result", "", terminal.type])
    return "\n".join(lines) + "\n"


def _run_duration(events: list[RuntimeEvent]) -> float | None:
    started = next((event for event in events if event.type == "run.started"), None)
    finished = terminal_event(events)
    return _duration(started.ts, finished.ts) if started and finished else None


def _paired_durations(
    events: Iterable[RuntimeEvent], prefix: str, identity: str
) -> dict[str, float]:
    starts: dict[str, list[str]] = defaultdict(list)
    totals: dict[str, float] = defaultdict(float)
    for event in events:
        if prefix == "workflow.step":
            key = event.step_id
        elif prefix == "agent":
            key = event.agent_id
        else:
            key = event.payload.get(identity)
        if not key:
            continue
        key = str(key)
        if event.type == f"{prefix}.started":
            starts[key].append(event.ts)
        elif event.type in {f"{prefix}.completed", f"{prefix}.failed"} and starts[key]:
            totals[key] += _duration(starts[key].pop(0), event.ts)
    return {key: round(value, 6) for key, value in sorted(totals.items())}


def _validation_status(events: list[RuntimeEvent]) -> str:
    if not events:
        return "not_run"
    terminal_by_step: dict[str, RuntimeEvent] = {}
    for event in events:
        if event.type.endswith((".completed", ".failed")):
            key = event.step_id or str(event.payload.get("tool", "validation"))
            terminal_by_step[key] = event
    if any(event.type.endswith(".failed") for event in terminal_by_step.values()):
        return "failed"
    if any(event.type.endswith(".completed") for event in terminal_by_step.values()):
        return "passed"
    return "running"


def _duration(start: str, end: str) -> float:
    start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return round(max(0.0, (end_time - start_time).total_seconds()), 6)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
