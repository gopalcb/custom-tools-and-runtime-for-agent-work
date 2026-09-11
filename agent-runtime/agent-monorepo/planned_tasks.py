"""Persist implementation planner task breakdowns for controller tracking.

This module owns the durable task projection under
``agent-runtime/controller-data-store/planned-tasks``. Planner entry points
write task manifests here, and task execution updates the matching YAML entry.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml


TASK_STATUSES = {"awaiting implementation", "implementing", "complete", "need rework"}
NAME_PATTERN = re.compile(r"[^a-z0-9]+")
FENCED_JSON_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
STATUS_REPORT_PATTERN = re.compile(
    r"planned-task\s+`?([a-z0-9]+(?:-[a-z0-9]+)*)`?\s*[:=-]\s*"
    r"(awaiting implementation|implementing|complete|need rework)",
    re.IGNORECASE,
)


def utc_now_iso() -> str:
    """Return the current UTC timestamp in repository event format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def planned_tasks_root(project_root: str | Path) -> Path:
    """Return the repository-local planned task data store root."""
    return Path(project_root).resolve() / "agent-runtime" / "controller-data-store" / "planned-tasks"


def safe_name(value: str, fallback: str = "task") -> str:
    """Convert a title or task label into a safe lowercase file stem."""
    cleaned = NAME_PATTERN.sub("-", value.strip().lower()).strip("-")
    return cleaned or fallback


def extract_structured_plan(text: str) -> dict[str, Any] | None:
    """Extract a JSON plan object from a planner response when one is present."""
    stripped = text.strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(match.group(1) for match in FENCED_JSON_PATTERN.finditer(stripped))
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def persist_planned_tasks(
    project_root: str | Path,
    plan: Mapping[str, Any],
    run_id: str | None = None,
    session_id: str | None = None,
) -> Path:
    """Write a validated plan task breakdown and return its manifest path."""
    title = str(plan.get("title") or "implementation-plan").strip()
    plan_id = safe_name(title, "implementation-plan")
    plan_dir = planned_tasks_root(project_root) / plan_id
    manifest_path = plan_dir / "tasks.yaml"
    existing = read_manifest(manifest_path)
    existing_plan = existing.get("plan") if isinstance(existing.get("plan"), dict) else {}
    existing_tasks = {str(task.get("id")): task for task in existing.get("tasks", []) if isinstance(task, dict)}
    now = utc_now_iso()
    tasks = []
    for index, raw_task in enumerate(plan.get("tasks") or [], 1):
        if not isinstance(raw_task, Mapping):
            continue
        task_id = safe_name(str(raw_task.get("name") or raw_task.get("id") or raw_task.get("title") or index), f"task-{index}")
        previous = existing_tasks.get(task_id, {})
        status = str(previous.get("status") or "awaiting implementation")
        if status not in TASK_STATUSES:
            status = "awaiting implementation"
        created_at = str(previous.get("created_at") or now)
        updated_at = str(previous.get("updated_at") or now)
        events = previous.get("events") if isinstance(previous.get("events"), list) else []
        if not events:
            events = [{"ts": now, "type": "task.planned", "status": status, "message": "Task created by implementation plan."}]
        task = {
            "id": task_id,
            "name": task_id,
            "label": "planned-task",
            "title": str(raw_task.get("title") or task_id),
            "description": str(raw_task.get("description") or ""),
            "status": status,
            "depends_on": string_list(raw_task.get("depends_on")),
            "files": string_list(raw_task.get("files")),
            "acceptance_criteria": string_list(raw_task.get("acceptance_criteria")),
            "markdown": f"{task_id}.md",
            "created_at": created_at,
            "updated_at": updated_at,
            "run_id": previous.get("run_id"),
            "session_id": previous.get("session_id"),
            "events": events[-100:],
        }
        tasks.append(task)
    manifest = {
        "version": 1,
        "plan": {
            "id": plan_id,
            "title": title,
            "summary": str(plan.get("summary") or ""),
            "workflow_id": str(plan.get("workflow_id") or ""),
            "created_at": str(existing_plan.get("created_at") or now),
            "updated_at": now,
            "source_run_id": run_id,
            "source_session_id": session_id,
        },
        "tasks": tasks,
    }
    plan_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        write_text_atomic(plan_dir / str(task["markdown"]), render_task_markdown(manifest["plan"], task))
    write_yaml_atomic(manifest_path, manifest)
    return manifest_path


def render_planned_task_handoff(plan: Mapping[str, Any], manifest_path: Path) -> str:
    """Render planner-created task identifiers for the next workflow step."""
    tasks = [task for task in plan.get("tasks") or [] if isinstance(task, Mapping)]
    if not tasks:
        return ""
    lines = [
        "# Planned Task Handoff",
        "",
        "The planning step created these planned-task identifiers. Work on them in dependency order.",
        f"Task manifest: `{manifest_path}`",
        "",
    ]
    for raw_task in tasks:
        task_id = safe_name(str(raw_task.get("name") or raw_task.get("id") or raw_task.get("title") or "task"))
        dependencies = ", ".join(string_list(raw_task.get("depends_on"))) or "none"
        files = ", ".join(string_list(raw_task.get("files"))) or "none"
        lines.extend(
            [
                f"- planned-task `{task_id}`: {raw_task.get('title', task_id)}",
                f"  Description: {raw_task.get('description', '')}",
                f"  Depends on: {dependencies}",
                f"  Files: {files}",
            ]
        )
    lines.extend(
        [
            "",
            "When you finish, report one status line per identifier using:",
            "`planned-task <identifier>: complete` or `planned-task <identifier>: need rework`.",
        ]
    )
    return "\n".join(lines)


def update_planned_tasks_from_report(
    project_root: str | Path,
    plan_id: str,
    report: str,
    run_id: str | None = None,
    session_id: str | None = None,
) -> int:
    """Apply explicit planned-task status lines from an agent report."""
    count = 0
    seen: set[tuple[str, str]] = set()
    for match in STATUS_REPORT_PATTERN.finditer(report):
        task_id = safe_name(match.group(1))
        status = match.group(2).lower()
        key = (task_id, status)
        if key in seen:
            continue
        seen.add(key)
        if update_planned_task_status(
            project_root,
            plan_id,
            task_id,
            status,
            f"Agent reported planned-task {task_id}: {status}.",
            run_id,
            session_id,
        ):
            count += 1
    return count


def update_planned_task_status(
    project_root: str | Path,
    plan_id: str,
    task_id: str,
    status: str,
    message: str,
    run_id: str | None = None,
    session_id: str | None = None,
) -> Path | None:
    """Update one planned task status when an execution task advances."""
    if status not in TASK_STATUSES:
        status = "awaiting implementation"
    manifest_path = find_manifest(project_root, plan_id)
    if manifest_path is None:
        return None
    manifest = read_manifest(manifest_path)
    plan = manifest.get("plan")
    tasks = manifest.get("tasks")
    if not isinstance(plan, dict) or not isinstance(tasks, list):
        return None
    now = utc_now_iso()
    changed = False
    normalized_task_id = safe_name(task_id)
    for task in tasks:
        if not isinstance(task, dict) or str(task.get("id")) != normalized_task_id:
            continue
        events = task.get("events") if isinstance(task.get("events"), list) else []
        events.append(
            {
                "ts": now,
                "type": "task.status",
                "status": status,
                "message": message,
                "details": {"run_id": run_id, "session_id": session_id},
            }
        )
        task["status"] = status
        task["updated_at"] = now
        task["run_id"] = run_id or task.get("run_id")
        task["session_id"] = session_id or task.get("session_id")
        task["events"] = events[-100:]
        changed = True
        write_text_atomic(manifest_path.parent / str(task.get("markdown") or f"{normalized_task_id}.md"), render_task_markdown(plan, task))
        break
    if not changed:
        return None
    plan["updated_at"] = now
    write_yaml_atomic(manifest_path, manifest)
    return manifest_path


def find_manifest(project_root: str | Path, plan_id: str) -> Path | None:
    """Find a planned-task manifest by plan id, directory name, or title."""
    root = planned_tasks_root(project_root)
    if not root.is_dir():
        return None
    normalized = safe_name(plan_id, "implementation-plan")
    direct = root / normalized / "tasks.yaml"
    if direct.is_file():
        return direct
    for path in sorted(root.glob("*/tasks.yaml")):
        manifest = read_manifest(path)
        plan = manifest.get("plan")
        if not isinstance(plan, dict):
            continue
        if normalized in {safe_name(str(plan.get("id") or "")), safe_name(str(plan.get("title") or ""))}:
            return path
    return None


def read_manifest(path: Path) -> dict[str, Any]:
    """Read a YAML manifest, returning an empty mapping when it is absent."""
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(value) if isinstance(value, dict) else {}


def string_list(value: Any) -> list[str]:
    """Return a list containing only non-empty string values."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def render_task_markdown(plan: Mapping[str, Any], task: Mapping[str, Any]) -> str:
    """Render one planned task as readable Markdown for controller drill-in."""
    lines = [
        f"# {task.get('title', task.get('id', 'Task'))}",
        "",
        f"- Plan: {plan.get('title', '')}",
        f"- Task: `{task.get('id', '')}`",
        f"- Status: `{task.get('status', 'awaiting implementation')}`",
        "",
        "## Description",
        "",
        str(task.get("description") or ""),
        "",
        "## Dependencies",
        "",
    ]
    dependencies = string_list(task.get("depends_on"))
    lines.extend(f"- `{dependency}`" for dependency in dependencies)
    if not dependencies:
        lines.append("- none")
    lines.extend(["", "## Files", ""])
    files = string_list(task.get("files"))
    lines.extend(f"- `{path}`" for path in files)
    if not files:
        lines.append("- none")
    lines.extend(["", "## Acceptance Criteria", ""])
    criteria = string_list(task.get("acceptance_criteria"))
    lines.extend(f"- {item}" for item in criteria)
    if not criteria:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_yaml_atomic(path: Path, value: Mapping[str, Any]) -> None:
    """Write YAML through a temporary file and atomic rename."""
    text = yaml.safe_dump(dict(value), sort_keys=False, allow_unicode=False)
    write_text_atomic(path, text)


def write_text_atomic(path: Path, value: str) -> None:
    """Write text through a temporary file and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
