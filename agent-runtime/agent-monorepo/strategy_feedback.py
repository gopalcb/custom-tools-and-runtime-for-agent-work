"""Collect post-work feedback and turn it into strategy-memory actions.

This module owns the interactive feedback subprocess and focused feedback
analysis turn. Runtime workflow control remains in runtime.py and durable
memory writes remain in memory/service.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from .events import utc_now


logger = logging.getLogger(__name__)


class StrategyFeedbackCoordinator:
    """Coordinate the feedback GUI and analyzer turn for one runtime."""

    def __init__(
        self,
        project_root: str | Path,
        registry: Any,
        codex: Any,
        memory: Any,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.registry = registry
        self.codex = codex
        self.memory = memory

    def enabled(self) -> bool:
        """Return whether interactive strategy feedback is enabled."""
        if os.environ.get("AGENT_STRATEGY_FEEDBACK", "").casefold() in {"0", "false", "no", "off"}:
            return False
        memory_config = self.registry.project_config.get("memory", {})
        if not isinstance(memory_config, dict) or not memory_config.get("enabled", False):
            return False
        feedback_config = memory_config.get("strategy_feedback", {})
        return isinstance(feedback_config, dict) and bool(feedback_config.get("enabled", False))

    def settings(self) -> dict[str, Any]:
        """Return strategy-feedback settings with conservative defaults."""
        memory_config = self.registry.project_config.get("memory", {})
        feedback_config = memory_config.get("strategy_feedback", {}) if isinstance(memory_config, dict) else {}
        if not isinstance(feedback_config, dict):
            feedback_config = {}
        return {
            "max_rework_cycles": int(feedback_config.get("max_rework_cycles", 3)),
            "feedback_timeout_seconds": int(feedback_config.get("feedback_timeout_seconds", 600)),
        }

    async def collect_feedback(self, context: Any) -> dict[str, Any]:
        """Start the feedback GUI and return the submitted or cancelled payload."""
        run_dir = context.event_hub.run_dir(context.session_id, context.run_id, create=True)
        output_path = run_dir / "strategy-feedback.json"
        fixture_path = os.environ.get("AGENT_STRATEGY_FEEDBACK_RESPONSE")
        if fixture_path:
            payload = load_feedback_response(Path(fixture_path))
            write_feedback_response(output_path, payload)
            return {**payload, "artifact_path": str(output_path)}

        script_path = self.project_root / "agent-tools" / "strategy-feedback" / "strategy_feedback_gui.py"
        if not script_path.is_file():
            return {
                "status": "unavailable",
                "reason": f"Feedback GUI script is missing: {script_path}",
            }

        settings = self.settings()
        command = [
            sys.executable,
            str(script_path),
            "--run-id",
            context.run_id,
            "--session-id",
            context.session_id,
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
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=float(settings["feedback_timeout_seconds"]),
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return {"status": "timeout", "artifact_path": str(output_path)}
        except asyncio.CancelledError:
            process.kill()
            await process.communicate()
            raise

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

    async def analyze_feedback(self, context: Any, feedback: Mapping[str, Any]) -> dict[str, Any]:
        """Ask the strategy-memory analyzer to classify feedback and propose actions."""
        try:
            analyzer = self.registry.get_agent("strategy-memory-analyzer")
        except Exception:
            return fallback_analysis(feedback)
        prompt = build_analysis_prompt(context, feedback)
        final_parts: list[str] = []
        codex_options = self.registry.codex_options_for_profile(analyzer.model_profile)
        async for raw in self.codex.stream_turn(
            prompt,
            developer_instructions=analyzer.instructions,
            model=codex_options["model"],
            effort=codex_options["effort"],
            thread_id=None,
        ):
            method = str(raw.get("method") or "")
            params = raw.get("params") if isinstance(raw.get("params"), Mapping) else {}
            item = params.get("item") if isinstance(params.get("item"), Mapping) else {}
            if method == "item/agentMessage/delta":
                final_parts.append(str(params.get("delta") or ""))
            elif method == "item/completed" and item.get("type") == "agentMessage":
                text = item.get("text") or item.get("content")
                if text and not final_parts:
                    final_parts.append(str(text))
        analysis = parse_analysis("".join(final_parts))
        return analysis if analysis else fallback_analysis(feedback)


def build_analysis_prompt(context: Any, feedback: Mapping[str, Any]) -> str:
    """Render the compact analyzer prompt for a completed work attempt."""
    return (
        "Analyze this post-work user feedback for durable strategy memory and rework.\n\n"
        f"Original user request:\n{context.prompt}\n\n"
        f"Run id: {context.run_id}\n"
        f"Session id: {context.session_id}\n"
        f"Agent id: {context.agent_id}\n"
        f"Feedback payload:\n{json.dumps(dict(feedback), indent=2, ensure_ascii=False)}\n\n"
        "Return only JSON with feedback_type, rework, memory_actions, and reason."
    )


def parse_analysis(text: str) -> dict[str, Any]:
    """Parse a strict or fenced JSON analyzer response."""
    stripped = text.strip()
    if not stripped:
        return {}
    if "```" in stripped:
        parts = stripped.split("```")
        for part in parts:
            candidate = part.removeprefix("json").strip()
            parsed = parse_analysis(candidate)
            if parsed:
                return parsed
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Strategy feedback analyzer returned invalid JSON")
        return {}
    if not isinstance(parsed, dict):
        return {}
    actions = parsed.get("memory_actions")
    if not isinstance(actions, list):
        parsed["memory_actions"] = []
    rework = parsed.get("rework")
    if not isinstance(rework, dict):
        parsed["rework"] = {"needed": False, "prompt": ""}
    return parsed


def fallback_analysis(feedback: Mapping[str, Any]) -> dict[str, Any]:
    """Create a conservative local analysis when the analyzer is unavailable."""
    feedback_text = str(feedback.get("feedback") or "").strip()
    requested_change = str(feedback.get("requested_change") or "").strip()
    combined = f"{feedback_text}\n{requested_change}".strip()
    rework_needed = bool(requested_change)
    actions: list[dict[str, Any]] = []
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


def build_memory_source(context: Any, feedback: Mapping[str, Any]) -> dict[str, Any]:
    """Build source metadata for strategy-memory writes."""
    return {
        "session_id": context.session_id,
        "run_id": context.run_id,
        "feedback_artifact": feedback.get("artifact_path"),
        "created_at": utc_now(),
        "scope": {
            "repo": "agent-monorepo",
            "agent_id": context.agent_id,
            "workflow_id": context.resolved.workflow_id,
        },
    }


def load_feedback_response(path: Path) -> dict[str, Any]:
    """Load a GUI response payload from JSON."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "reason": str(exc)}
    if not isinstance(value, dict):
        return {"status": "unavailable", "reason": "Feedback response must be a JSON object."}
    return value


def write_feedback_response(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a feedback response artifact for this run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
