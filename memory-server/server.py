"""
Compact local memory-server operations for custom agent runtime state.

Records are deterministic JSON files under `.agent-state/cache/memory` with a
small lexical searcher; no vector store or external service is required.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def memory_root(project_root: str | Path = ".") -> Path:
    """Return the local memory state directory."""
    root = Path(project_root).resolve() / ".agent-state" / "cache" / "memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def health(project_root: str | Path = ".") -> dict:
    """Validate that memory storage can be read and written."""
    root = memory_root(project_root)
    probe = root / ".health.json"
    write_json(probe, {"ok": True})
    ok = json.loads(probe.read_text(encoding="utf-8")).get("ok") is True
    return {"alive": True, "ready": ok, "path": str(root)}


def store_memory(project_root: str | Path, payload: Mapping[str, Any], event: Mapping[str, Any] | None = None) -> dict:
    """Store one verified work memory as a retrievable JSON record."""
    request = required_text(payload, "original_task", "task")
    summary = required_text(payload, "summary")
    validation = required_text(payload, "validation")
    files = normalize_files(payload.get("file", payload.get("files")))
    created_at = timestamp(payload.get("created_at") or (event or {}).get("timestamp"))
    memory_id = memory_id_for(request, summary, validation, files)
    relative_path = Path("records") / str(payload.get("kind") or "regular-codex-work") / f"{memory_id}.json"
    root = memory_root(project_root)
    path = safe_record_path(root, relative_path)
    metadata = {
        "id": memory_id,
        "title": title_for(request),
        "kind": str(payload.get("kind") or "regular-codex-work"),
        "status": "active",
        "project": str(payload.get("project") or "custom-agent-tools-and-runtime"),
        "repo": str(payload.get("repo") or "custom-agent-tools-and-runtime"),
        "agent_id": payload.get("agent_id") or (event or {}).get("sender"),
        "source": {
            "type": "mq-message",
            "topic": (event or {}).get("topic"),
            "event_id": (event or {}).get("event_id"),
            "sender": (event or {}).get("sender"),
        },
        "created_at": created_at,
        "updated_at": created_at,
        "files": files,
        "tags": [str(tag) for tag in payload.get("tags", [])],
        "weight": float(payload.get("weight", 3.0)),
    }
    record = {
        "schema_version": 1,
        "id": memory_id,
        "path": relative_path.as_posix(),
        "content": render_content(request, summary, validation, files),
        "metadata": metadata,
    }
    write_json(path, record)
    return {"stored": 1, "memory_id": memory_id, "path": relative_path.as_posix()}


def search_memory(project_root: str | Path, payload: Mapping[str, Any]) -> dict:
    """Search active memory records with a compact lexical ranker."""
    query = required_text(payload, "query")
    limit = positive_int(payload.get("limit"), 5, 20)
    root = memory_root(project_root)
    query_tokens = tokens(query)
    results = []
    for record in load_records(root):
        metadata = dict(record.get("metadata") or {})
        if metadata.get("status") in {"superseded", "rejected", "needs_review"}:
            continue
        score = score_record(query, query_tokens, str(record.get("content", "")), metadata)
        if score <= 0:
            continue
        results.append(
            {
                "path": record.get("path"),
                "id": record.get("id"),
                "score": round(score, 8),
                "content": str(record.get("content", ""))[:2400],
                "metadata": metadata,
            }
        )
    results.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
    return {"query": query, "count": min(len(results), limit), "results": results[:limit]}


def required_text(payload: Mapping[str, Any], key: str, fallback_key: str | None = None) -> str:
    """Read a required non-secret text field."""
    value = payload.get(key)
    if (value is None or str(value).strip() == "") and fallback_key:
        value = payload.get(fallback_key)
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"memory payload requires {key}")
    if looks_secret_like(text):
        raise ValueError(f"memory payload {key} appears to contain a secret")
    return text


def normalize_files(value: Any) -> list[str]:
    """Normalize memory file references to safe relative paths."""
    if value is None:
        return []
    values = [value] if isinstance(value, (str, Path)) else value
    if not isinstance(values, list):
        raise ValueError("memory payload file/files must be a string or list")
    files = []
    for item in values:
        text = str(item).strip()
        if not text or text.startswith("/") or ".." in Path(text).parts:
            continue
        if text not in files:
            files.append(text)
    return files[:40]


def timestamp(value: Any) -> str:
    """Return a supplied timestamp or the current UTC timestamp."""
    return value.strip() if isinstance(value, str) and value.strip() else datetime.now(timezone.utc).isoformat()


def positive_int(value: Any, default: int, maximum: int) -> int:
    """Parse a bounded positive integer."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(1, parsed))


def memory_id_for(request: str, summary: str, validation: str, files: list[str]) -> str:
    """Build a deterministic memory id."""
    seed = json.dumps({"request": request, "summary": summary, "validation": validation, "files": files}, sort_keys=True, ensure_ascii=True)
    return f"codex-work-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def title_for(request: str) -> str:
    """Build a compact memory title."""
    return request.replace("\n", " ")[:120]


def render_content(request: str, summary: str, validation: str, files: list[str]) -> str:
    """Render searchable memory content."""
    lines = [f"Task: {request}", f"Summary: {summary}", f"Validation: {validation}"]
    if files:
        lines.append("Files: " + ", ".join(files))
    return "\n".join(lines)[:8000]


def safe_record_path(root: Path, relative: Path) -> Path:
    """Return a safe JSON record path below the memory root."""
    path = (root / relative).resolve()
    if path.suffix != ".json":
        raise ValueError("memory record path must be JSON")
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("memory path escapes memory root") from error
    return path


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically write one JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(dict(value), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_records(root: Path) -> list[dict]:
    """Load all JSON memory records below a memory root."""
    records = []
    records_root = root / "records"
    if not records_root.is_dir():
        return records
    for path in sorted(records_root.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and isinstance(record.get("content"), str):
            record["path"] = path.relative_to(root).as_posix()
            records.append(record)
    return records


def tokens(value: str) -> set[str]:
    """Tokenize text for lexical memory search."""
    return {match.group(0).lower() for match in TOKEN.finditer(value)}


def score_record(query: str, query_tokens: set[str], content: str, metadata: Mapping[str, Any]) -> float:
    """Score a memory record for a query."""
    if not query_tokens:
        return 0.0
    searchable_metadata = " ".join(str(metadata.get(key, "")) for key in ("title", "tags", "agent_id", "project", "kind"))
    matched = query_tokens & tokens(f"{content} {searchable_metadata}")
    if not matched:
        return 0.0
    phrase_bonus = 0.25 if query.strip().lower() in content.lower() else 0.0
    try:
        weight = min(4.0, max(0.0, float(metadata.get("weight", 1.0))))
    except (TypeError, ValueError):
        weight = 1.0
    return ((len(matched) / len(query_tokens)) + phrase_bonus) * weight


def looks_secret_like(value: str) -> bool:
    """Return whether text looks like a secret assignment."""
    return bool(re.search(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[A-Za-z0-9_.-]{12,}", value))
