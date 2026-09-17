"""
Dispatches compact MQ events to deterministic runtime operations.

Supported topics cover tasks, file IO, memory store/search, workflow resolution,
health, and simple system-error task creation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
MEMORY_SERVER = ROOT / "memory-server" / "server.py"
WORKFLOW_ENGINE = ROOT / "workflow" / "engine.py"


def load_module(name: str, path: Path) -> Any:
    """Load a sibling compact module by path."""
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


memory_server = load_module("compact_memory_server", MEMORY_SERVER)
workflow_engine = load_module("compact_workflow_engine", WORKFLOW_ENGINE)


def process_event(project_root: str | Path, event: dict) -> dict:
    """Process one MQ event and return a deterministic result."""
    topic = str(event.get("topic") or "").strip()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if topic == "todo":
        return save_todo(project_root, event, payload)
    if topic == "read-file":
        return {"content": read_text(project_root, payload["path"])}
    if topic == "write-file":
        path = write_text(project_root, payload["path"], str(payload.get("content", "")))
        return {"path": str(path)}
    if topic == "update-file":
        path = write_json(project_root, payload["path"], payload.get("content", {}))
        return {"path": str(path)}
    if topic == "delete-file":
        return {"deleted": delete_file(project_root, payload["path"])}
    if topic == "run-workflow":
        return workflow_engine.resolve_workflow_request(project_root, payload)
    if topic == "memory-store":
        return memory_server.store_memory(project_root, payload, event)
    if topic == "memory-search":
        return memory_server.search_memory(project_root, payload)
    if topic == "memory-health":
        return memory_server.health(project_root)
    if topic == "memory":
        return process_memory_request(project_root, event, payload)
    if topic == "invoke-function":
        return invoke_function(project_root, payload)
    if topic == "system-error":
        return save_system_error(project_root, event, payload)
    raise ValueError(f"Unsupported MQ topic: {topic}")


def process_memory_request(project_root: str | Path, event: dict, payload: dict) -> dict:
    """Dispatch generic memory messages to memory operations."""
    action = str(payload.get("action") or "store").strip().casefold()
    if action in {"store", "remember", "add"}:
        return memory_server.store_memory(project_root, payload, event)
    if action in {"search", "retrieve", "query"}:
        return memory_server.search_memory(project_root, payload)
    if action == "health":
        return memory_server.health(project_root)
    raise ValueError(f"Unsupported memory action: {action}")


def invoke_function(project_root: str | Path, payload: dict) -> dict:
    """Dispatch supported deterministic helper functions."""
    name = str(payload.get("name") or "").strip()
    if name == "health":
        return {"ok": True, "project_root": str(Path(project_root).resolve())}
    if name == "web-search":
        return {"ok": True, "message": "Use agent-custom-tools/knowledge-search/web_search.py", "query": payload.get("query", "")}
    raise ValueError(f"Unsupported function: {name}")


def save_todo(project_root: str | Path, event: dict, payload: dict) -> dict:
    """Persist a task/TODO record."""
    task_id = str(payload.get("id") or event.get("event_id"))
    project = str(payload.get("project") or "custom-agent-tools-and-runtime")
    record = {
        "id": task_id,
        "title": payload.get("title", task_id),
        "description": payload.get("description", ""),
        "status": payload.get("status", "open"),
        "action_required": payload.get("action_required", True),
        "source_event_id": event.get("event_id"),
    }
    for key in ("workflow", "phase", "depends_on", "files", "acceptance_criteria"):
        if key in payload:
            record[key] = payload[key]
    path = LocalStore(project_root).save_task(project, task_id, record)
    return {"task_id": task_id, "path": str(path)}


def save_system_error(project_root: str | Path, event: dict, payload: dict) -> dict:
    """Persist a system-error TODO for later remediation."""
    task_payload = {
        "id": payload.get("task_id") or f"task-{event.get('event_id')}",
        "project": payload.get("project", "custom-agent-tools-and-runtime"),
        "title": payload.get("title", "System error"),
        "description": payload.get("message", ""),
        "status": "open",
        "action_required": True,
    }
    return save_todo(project_root, event, task_payload)


def safe_project_path(project_root: str | Path, relative: str | Path) -> Path:
    """Resolve a safe path under the project root."""
    root = Path(project_root).resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("path escapes project root") from error
    return path


def read_text(project_root: str | Path, relative: str | Path) -> str:
    """Read a safe project file."""
    return safe_project_path(project_root, relative).read_text(encoding="utf-8")


def write_text(project_root: str | Path, relative: str | Path, content: str) -> Path:
    """Write a safe project file."""
    path = safe_project_path(project_root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(project_root: str | Path, relative: str | Path, content: Any) -> Path:
    """Write a safe project JSON file."""
    path = safe_project_path(project_root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def delete_file(project_root: str | Path, relative: str | Path) -> bool:
    """Delete a safe project file when present."""
    path = safe_project_path(project_root, relative)
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError("delete-file only removes files")
    path.unlink()
    return True
