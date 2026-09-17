"""
Coordinates compact post-work feedback collection and analysis.

The GUI remains in strategy_feedback_gui.py; this module handles fixture input,
headless fallback, analyzer JSON parsing, and durable memory-action shaping.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StrategyFeedbackCoordinator:
    """Collect and analyze feedback for one compact runtime run."""

    def __init__(self, project_root: str | Path = ".", feedback_timeout_seconds: int = 600) -> None:
        """Create a coordinator rooted at one project."""
        self.project_root = Path(project_root).resolve()
        self.feedback_timeout_seconds = feedback_timeout_seconds

    async def collect_feedback(self, context: Mapping[str, Any]) -> dict:
        """Collect feedback from a fixture or the Tkinter GUI."""
        run_id = str(context.get("run_id") or "run")
        session_id = str(context.get("session_id") or "session")
        output_path = Path(context.get("output") or self.project_root / ".agent-state" / "strategy-feedback" / run_id / "strategy-feedback.json")
        fixture_path = os.environ.get("AGENT_STRATEGY_FEEDBACK_RESPONSE")
        if fixture_path:
            payload = load_feedback_response(Path(fixture_path))
            write_feedback_response(output_path, payload)
            return {**payload, "artifact_path": str(output_path)}

        script_path = Path(__file__).resolve().with_name("strategy_feedback_gui.py")
        command = [
            sys.executable,
            str(script_path),
            "--run-id",
            run_id,
            "--session-id",
            session_id,
            "--output",
            str(output_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(self.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=float(self.feedback_timeout_seconds))
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return {"status": "timeout", "artifact_path": str(output_path)}

        if output_path.is_file():
            payload = load_feedback_response(output_path)
            return {**payload, "artifact_path": str(output_path)}
        if process.returncode:
            return {
                "status": "unavailable",
                "stdout": stdout.decode(errors="replace")[-2000:],
                "stderr": stderr.decode(errors="replace")[-2000:],
            }
        return {"status": "cancelled"}

    async def analyze_feedback(self, context: Mapping[str, Any], feedback: Mapping[str, Any], codex: Any | None = None) -> dict:
        """Analyze feedback with an optional Codex-like client or local fallback."""
        if codex is None:
            return fallback_analysis(feedback)
        prompt = build_analysis_prompt(context, feedback)
        response = await codex(prompt)
        analysis = parse_analysis(str(response))
        return analysis if analysis else fallback_analysis(feedback)


def build_analysis_prompt(context: Mapping[str, Any], feedback: Mapping[str, Any]) -> str:
    """Render a compact analyzer prompt for post-work feedback."""
    return (
        "Analyze this post-work user feedback for durable strategy memory and rework.\n\n"
        f"Original user request:\n{context.get('prompt', '')}\n\n"
        f"Run id: {context.get('run_id', '')}\n"
        f"Session id: {context.get('session_id', '')}\n"
        f"Agent id: {context.get('agent_id', '')}\n"
        f"Feedback payload:\n{json.dumps(dict(feedback), indent=2, ensure_ascii=False)}\n\n"
        "Return only JSON with feedback_type, rework, memory_actions, and reason."
    )


def parse_analysis(text: str) -> dict:
    """Parse strict or fenced JSON feedback analysis."""
    stripped = text.strip()
    if not stripped:
        return {}
    if "```" in stripped:
        for part in stripped.split("```"):
            parsed = parse_analysis(part.removeprefix("json").strip())
            if parsed:
                return parsed
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    if not isinstance(parsed.get("memory_actions"), list):
        parsed["memory_actions"] = []
    if not isinstance(parsed.get("rework"), dict):
        parsed["rework"] = {"needed": False, "prompt": ""}
    return parsed


def fallback_analysis(feedback: Mapping[str, Any]) -> dict:
    """Create conservative feedback analysis without a model call."""
    feedback_text = str(feedback.get("feedback") or "").strip()
    requested_change = str(feedback.get("requested_change") or "").strip()
    combined = f"{feedback_text}\n{requested_change}".strip()
    rework_needed = bool(requested_change)
    actions = []
    if combined and bool(feedback.get("store_work_memory", True)):
        actions.append(
            {
                "action": "add",
                "kind": "user-work-strategy",
                "subject": "User feedback on completed work",
                "content": combined[:1200],
                "confidence": 0.65,
            }
        )
    return {
        "feedback_type": "rework_request" if rework_needed else ("preference" if combined else "no_action"),
        "rework": {"needed": rework_needed, "prompt": requested_change},
        "memory_actions": actions,
        "reason": "Local fallback analysis used.",
    }


def build_memory_source(context: Mapping[str, Any], feedback: Mapping[str, Any]) -> dict:
    """Build source metadata for strategy-memory writes."""
    return {
        "session_id": context.get("session_id"),
        "run_id": context.get("run_id"),
        "feedback_artifact": feedback.get("artifact_path"),
        "created_at": utc_now(),
        "scope": {
            "repo": context.get("repo", "custom-agent-tools-and-runtime"),
            "agent_id": context.get("agent_id"),
            "workflow_id": context.get("workflow_id"),
        },
    }


def load_feedback_response(path: Path) -> dict:
    """Load a feedback response artifact."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {"status": "unavailable", "reason": str(error)}
    return value if isinstance(value, dict) else {"status": "unavailable", "reason": "Feedback response must be a JSON object."}


def write_feedback_response(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a feedback response artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
