"""Local work-memory extraction, storage, and lexical retrieval.

The service derives deterministic memory candidates from RuntimeEvents at run
finalization time. Approved candidates are stored as JSON records under the
configured memory root and can be retrieved by later runs without an external
index or model call.
"""

from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from .retrieval import MemoryHit, MemoryRetriever

if TYPE_CHECKING:
    from ..events import RuntimeEvent


logger = logging.getLogger(__name__)
TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})
SAFE_FRAGMENT = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    retrieval_enabled: bool = False
    extraction_enabled: bool = False


class MemoryService:
    """Own deterministic local memory extraction and retrieval policy."""

    def __init__(
        self,
        memory_root: str | Path,
        policy: MemoryPolicy | None = None,
        *,
        retrieval_enabled: bool | None = None,
        extraction_enabled: bool | None = None,
    ) -> None:
        base = policy or MemoryPolicy()
        self.policy = MemoryPolicy(
            retrieval_enabled=(
                base.retrieval_enabled
                if retrieval_enabled is None
                else retrieval_enabled
            ),
            extraction_enabled=(
                base.extraction_enabled
                if extraction_enabled is None
                else extraction_enabled
            ),
        )
        self.retriever = MemoryRetriever(memory_root)
        self.records_root = self.retriever.memory_root / "records"
        logger.info(
            "MemoryService initialized",
            extra={
                "memory_root": str(memory_root),
                "retrieval_enabled": self.policy.retrieval_enabled,
                "extraction_enabled": self.policy.extraction_enabled,
            },
        )

    def retrieve(
        self,
        query: str,
        records: Iterable[Mapping[str, Any]],
        *,
        allowed_paths: Sequence[str | Path] | None = None,
        metadata_filter: Mapping[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryHit]:
        """Rank supplied memory records when retrieval policy is enabled."""
        if not self.policy.retrieval_enabled:
            logger.info("Memory retrieval skipped because policy is disabled")
            return []
        hits = self.retriever.retrieve(
            query,
            records,
            allowed_paths=allowed_paths,
            metadata_filter=metadata_filter,
            limit=limit,
        )
        logger.info("Memory retrieval completed", extra={"hit_count": len(hits), "limit": limit})
        return hits

    def should_extract(self, _events: Iterable["RuntimeEvent"] | None = None) -> bool:
        """Return whether finalization should derive memory candidates."""
        logger.info("Memory extraction policy checked", extra={"enabled": self.policy.extraction_enabled})
        return self.policy.extraction_enabled

    def prepare_candidates(
        self,
        events: Iterable["RuntimeEvent"],
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Build, persist, and optionally write event-derived memory candidates."""
        event_list = list(events)
        result: dict[str, Any] = {
            "status": "enabled" if self.policy.extraction_enabled else "disabled",
            "candidates": [],
        }
        if self.policy.extraction_enabled:
            result = self.build_candidate_document(event_list)
            stored_paths = self.store_candidates(result)
            result["stored_records"] = [path.as_posix() for path in stored_paths]
        if output_path is not None:
            _write_json(Path(output_path), result)
        logger.info(
            "Memory candidates prepared",
            extra={"status": result["status"], "candidate_count": len(result["candidates"])},
        )
        return result

    def build_candidate_document(self, events: Sequence["RuntimeEvent"]) -> dict[str, Any]:
        """Derive a stable memory-candidate document from one run's events."""
        if not events:
            return {
                "status": "empty",
                "candidates": [],
            }
        first = events[0]
        terminal = latest_terminal_event(events) or events[-1]
        started = next((event for event in events if event.type == "run.started"), first)
        resolver = next((event for event in events if event.type == "resolver.completed"), None)
        workflow_selection = next(
            (event for event in reversed(events) if event.type == "workflow.resolved"),
            None,
        )
        agent_ids = sorted({event.agent_id for event in events if event.agent_id})
        changed_paths = sorted(
            {
                str(event.payload["path"])
                for event in events
                if event.type == "file.changed" and event.payload.get("path")
            }
        )
        artifact_paths = sorted(
            {
                str(event.payload["path"])
                for event in events
                if event.type == "artifact.created" and event.payload.get("path")
            }
        )
        failures = collect_failure_events(events)
        status = {
            "run.completed": "completed",
            "run.failed": "failed",
            "run.cancelled": "cancelled",
        }.get(terminal.type, "running")
        base_metadata = {
            "project": "agent-monorepo",
            "run_id": first.run_id,
            "session_id": first.session_id,
            "status": status,
            "agent_ids": agent_ids,
            "agent_id": resolver.payload.get("agent_id") if resolver else (agent_ids[0] if agent_ids else None),
            "workflow_id": resolver.payload.get("workflow_id") if resolver else None,
            "selected_workflow_id": workflow_selection.payload.get("workflow_id") if workflow_selection else None,
            "created_at": terminal.ts,
            "updated_at": terminal.ts,
            "tags": ["run", status, *agent_ids],
            "weight": 1.5 if status == "completed" else 2.0,
        }
        candidates = [
            build_candidate(
                first.session_id,
                first.run_id,
                "run-summary",
                "Run summary",
                render_run_summary(
                    started.message,
                    status,
                    terminal.message,
                    resolver.payload if resolver else {},
                    workflow_selection.payload if workflow_selection else {},
                    changed_paths,
                    artifact_paths,
                    failures,
                ),
                {**base_metadata, "kind": "run-summary"},
            )
        ]
        if failures:
            candidates.append(
                build_candidate(
                    first.session_id,
                    first.run_id,
                    "failure-summary",
                    "Failure summary",
                    render_failure_summary(failures),
                    {
                        **base_metadata,
                        "kind": "failure-summary",
                        "tags": [*base_metadata["tags"], "error", "failure"],
                        "weight": 2.5,
                    },
                )
            )
        if changed_paths or artifact_paths:
            candidates.append(
                build_candidate(
                    first.session_id,
                    first.run_id,
                    "change-summary",
                    "Changed files and artifacts",
                    render_change_summary(changed_paths, artifact_paths),
                    {
                        **base_metadata,
                        "kind": "change-summary",
                        "tags": [*base_metadata["tags"], "files", "artifacts"],
                    },
                )
            )
        return {
            "status": "ready",
            "run_id": first.run_id,
            "session_id": first.session_id,
            "generated_at": terminal.ts,
            "candidates": candidates,
        }

    def store_candidates(self, document: Mapping[str, Any]) -> list[Path]:
        """Write candidate records under the memory root and return relative paths."""
        if document.get("status") != "ready":
            return []
        stored: list[Path] = []
        for candidate in document.get("candidates", []):
            if not isinstance(candidate, Mapping):
                continue
            path = safe_record_path(self.retriever.memory_root, candidate.get("path"))
            if path is None:
                continue
            _write_json(path, candidate)
            stored.append(path.relative_to(self.retriever.memory_root))
        logger.info("Memory records stored", extra={"record_count": len(stored)})
        return stored

    def apply_strategy_memory_actions(
        self,
        actions: Sequence[Mapping[str, Any]],
        source: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply validated strategy-memory actions and preserve replaced records."""
        records = self.load_records()
        results: list[dict[str, Any]] = []
        for raw_action in actions[:8]:
            action = str(raw_action.get("action", "noop")).casefold()
            if action not in {"add", "update", "supersede", "noop"}:
                action = "noop"
            if action == "noop":
                results.append({"action": "noop", "status": "skipped"})
                continue

            content = str(raw_action.get("content") or "").strip()
            subject = str(raw_action.get("subject") or "").strip()
            kind = str(raw_action.get("kind") or "user-work-strategy").strip()
            if not usable_strategy_content(content, subject, kind):
                results.append({"action": action, "status": "rejected", "reason": "low-signal"})
                continue

            existing = find_strategy_record(records, raw_action)
            supersedes: list[str] = []
            if existing is not None and action in {"update", "supersede"}:
                existing_metadata = dict(existing.get("metadata") or {})
                existing_metadata["status"] = "superseded"
                existing_metadata["superseded_at"] = source.get("created_at")
                existing["metadata"] = existing_metadata
                path = safe_record_path(self.retriever.memory_root, existing.get("path"))
                if path is not None:
                    _write_json(path, existing)
                supersedes.append(str(existing.get("id") or existing_metadata.get("id") or ""))
            elif existing is not None and action == "add":
                results.append(
                    {
                        "action": "noop",
                        "status": "duplicate",
                        "memory_id": existing.get("id"),
                        "path": existing.get("path"),
                    }
                )
                continue

            record = build_strategy_record(raw_action, source, supersedes)
            path = safe_record_path(self.retriever.memory_root, record.get("path"))
            if path is None:
                results.append({"action": action, "status": "rejected", "reason": "unsafe-path"})
                continue
            _write_json(path, record)
            results.append(
                {
                    "action": action,
                    "status": "stored",
                    "memory_id": record["id"],
                    "path": record["path"],
                    "supersedes": supersedes,
                }
            )

        stored = sum(1 for result in results if result.get("status") == "stored")
        return {"status": "completed", "stored": stored, "results": results}

    def load_records(self) -> list[dict[str, Any]]:
        """Load stored memory records from the local records tree."""
        if not self.records_root.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.records_root.rglob("*.json")):
            record = read_record(path)
            if record is None:
                continue
            relative = path.relative_to(self.retriever.memory_root).as_posix()
            if record.get("path") != relative:
                record["path"] = relative
            records.append(record)
        logger.info("Memory records loaded", extra={"record_count": len(records)})
        return records

    def retrieve_context(self, query: str, limit: int = 5) -> str:
        """Return a compact text block of relevant stored memory for a prompt."""
        if not self.policy.retrieval_enabled:
            return ""
        records = [
            record
            for record in self.load_records()
            if dict(record.get("metadata") or {}).get("status")
            not in {"superseded", "rejected", "needs_review"}
        ]
        hits = self.retrieve(query, records, limit=limit)
        if not hits:
            return ""
        sections: list[str] = []
        for hit in hits:
            kind = hit.metadata.get("kind", "memory")
            title = hit.metadata.get("title") or kind
            confidence = hit.metadata.get("confidence")
            confidence_text = f", confidence {confidence}" if confidence is not None else ""
            sections.append(
                f"### {title} ({hit.path}, score {hit.score}{confidence_text})\n"
                f"{hit.content[:2400].rstrip()}"
            )
        return "\n\n".join(sections)


def latest_terminal_event(events: Sequence["RuntimeEvent"]) -> "RuntimeEvent" | None:
    """Return the most recent terminal run event from a sequence."""
    return next((event for event in reversed(events) if event.type in TERMINAL_EVENTS), None)


def collect_failure_events(events: Sequence["RuntimeEvent"]) -> list[dict[str, Any]]:
    """Collect unique error and failed-step messages from the event stream."""
    failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()
    for event in events:
        if event.type not in {"error", "workflow.step.failed", "tool.failed", "background.failed"}:
            continue
        message = str(event.message or event.payload.get("error") or "").strip()
        if not message:
            continue
        key = (event.type, event.step_id, message)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            {
                "type": event.type,
                "step_id": event.step_id,
                "agent_id": event.agent_id,
                "message": message[:4000],
                "ts": event.ts,
            }
        )
    return failures


def build_candidate(
    session_id: str,
    run_id: str,
    candidate_id: str,
    title: str,
    content: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one retrievable memory candidate record."""
    safe_session = safe_fragment(session_id)
    safe_run = safe_fragment(run_id)
    safe_id = safe_fragment(candidate_id)
    return {
        "id": safe_id,
        "path": f"records/{safe_session}/{safe_run}/{safe_id}.json",
        "content": content.strip()[:8000],
        "metadata": {"title": title, **dict(metadata)},
    }


def build_strategy_record(
    action: Mapping[str, Any],
    source: Mapping[str, Any],
    supersedes: Sequence[str],
) -> dict[str, Any]:
    """Create a durable strategy-memory record from an analyzer action."""
    kind = safe_fragment(action.get("kind") or "user-work-strategy")
    subject = str(action.get("subject") or "Work strategy").strip()[:200]
    content = str(action.get("content") or "").strip()[:4000]
    scope = source.get("scope") if isinstance(source.get("scope"), Mapping) else {}
    confidence = strategy_confidence(action.get("confidence"))
    memory_id = strategy_memory_id(kind, subject, content, scope)
    now = str(source.get("created_at") or "")
    return {
        "schema_version": 1,
        "id": memory_id,
        "path": f"records/strategy/{memory_id}.json",
        "content": content,
        "metadata": {
            "id": memory_id,
            "title": subject,
            "kind": kind,
            "status": "active",
            "subject": subject,
            "project": scope.get("repo") or "agent-monorepo",
            "repo": scope.get("repo") or "agent-monorepo",
            "agent_id": scope.get("agent_id"),
            "workflow_id": scope.get("workflow_id"),
            "confidence": confidence,
            "source": dict(source),
            "created_at": now,
            "updated_at": now,
            "supersedes": [item for item in supersedes if item],
            "tags": ["user-preference", "strategy", kind],
            "weight": 3.5,
        },
    }


def find_strategy_record(
    records: Sequence[Mapping[str, Any]],
    action: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Find the active strategy record targeted by an analyzer action."""
    target_id = str(action.get("memory_id") or "").strip()
    subject = str(action.get("subject") or "").strip().casefold()
    kind = str(action.get("kind") or "user-work-strategy").strip()
    for record in records:
        metadata = dict(record.get("metadata") or {})
        if metadata.get("status") != "active":
            continue
        if target_id and target_id in {str(record.get("id")), str(metadata.get("id"))}:
            return record
        if (
            subject
            and subject == str(metadata.get("subject") or metadata.get("title") or "").casefold()
            and kind == str(metadata.get("kind") or "")
        ):
            return record
    return None


def usable_strategy_content(content: str, subject: str, kind: str) -> bool:
    """Return whether a strategy-memory proposal has enough durable signal."""
    if kind not in {"user-work-strategy", "user-preference", "retrieval-feedback"}:
        return False
    if len(content) < 24 or len(subject) < 3:
        return False
    secret_like = re.search(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[A-Za-z0-9_.-]{12,}",
        content,
    )
    return secret_like is None


def strategy_confidence(value: Any) -> float:
    """Normalize analyzer confidence to the accepted range."""
    try:
        return round(min(1.0, max(0.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.7


def strategy_memory_id(
    kind: str,
    subject: str,
    content: str,
    scope: Mapping[str, Any],
) -> str:
    """Build a stable record id for one active strategy memory."""
    seed = json.dumps(
        {
            "kind": kind,
            "subject": subject.casefold(),
            "content": content.casefold(),
            "repo": scope.get("repo"),
            "agent_id": scope.get("agent_id"),
            "workflow_id": scope.get("workflow_id"),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"strategy-{safe_fragment(kind)}-{digest}"


def render_run_summary(
    request: str | None,
    status: str,
    final_message: str | None,
    resolver_payload: Mapping[str, Any],
    workflow_payload: Mapping[str, Any],
    changed_paths: Sequence[str],
    artifact_paths: Sequence[str],
    failures: Sequence[Mapping[str, Any]],
) -> str:
    """Render a compact memory summary for one run."""
    lines = [
        f"Request: {request or 'No request captured.'}",
        f"Status: {status}",
    ]
    agent_id = resolver_payload.get("agent_id")
    if agent_id:
        lines.append(f"Resolved agent: {agent_id}")
    workflow_id = resolver_payload.get("workflow_id")
    if workflow_id:
        lines.append(f"Initial workflow: {workflow_id}")
    selected_workflow = workflow_payload.get("workflow_id")
    if selected_workflow:
        lines.append(f"Selected workflow: {selected_workflow}")
    if changed_paths:
        lines.append("Changed files: " + ", ".join(changed_paths[:40]))
    if artifact_paths:
        lines.append("Artifacts: " + ", ".join(artifact_paths[:40]))
    if failures:
        failure_messages: list[str] = []
        for item in failures:
            message = str(item["message"])
            if message not in failure_messages:
                failure_messages.append(message)
            if len(failure_messages) == 5:
                break
        lines.append("Failures: " + " | ".join(failure_messages))
    if final_message:
        lines.append(f"Final message: {final_message[:2000]}")
    return "\n".join(lines)


def render_failure_summary(failures: Sequence[Mapping[str, Any]]) -> str:
    """Render failure events as a retrievable memory record."""
    lines = ["Failure events:"]
    for failure in failures[:20]:
        step = f" step={failure['step_id']}" if failure.get("step_id") else ""
        lines.append(f"- {failure['type']}{step}: {failure['message']}")
    return "\n".join(lines)


def render_change_summary(changed_paths: Sequence[str], artifact_paths: Sequence[str]) -> str:
    """Render changed files and artifacts as a retrievable memory record."""
    lines: list[str] = []
    if changed_paths:
        lines.append("Changed files:")
        lines.extend(f"- {path}" for path in changed_paths[:80])
    if artifact_paths:
        lines.append("Artifacts:")
        lines.extend(f"- {path}" for path in artifact_paths[:80])
    return "\n".join(lines)


def safe_fragment(value: Any) -> str:
    """Return a filesystem-safe identifier fragment."""
    cleaned = SAFE_FRAGMENT.sub("-", str(value or "")).strip(".-")
    return cleaned[:120] or "memory"


def safe_record_path(memory_root: Path, value: Any) -> Path | None:
    """Resolve a candidate record path beneath the memory root."""
    if not isinstance(value, str) or not value:
        return None
    raw = Path(value)
    if raw.is_absolute():
        return None
    path = (memory_root / raw).resolve()
    try:
        path.relative_to(memory_root)
    except ValueError:
        return None
    if path.suffix != ".json":
        return None
    return path


def read_record(path: Path) -> dict[str, Any] | None:
    """Read one stored memory record if it has the expected shape."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Skipping unreadable memory record", extra={"path": str(path)})
        return None
    if not isinstance(value, dict) or not isinstance(value.get("content"), str):
        return None
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        value["metadata"] = {}
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
