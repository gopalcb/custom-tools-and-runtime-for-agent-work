from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_source_package() -> None:
    """Load the source package for direct test execution."""
    if "agent_monorepo" in sys.modules:
        return
    package_dir = ROOT / "agent-runtime" / "agent-monorepo"
    spec = importlib.util.spec_from_file_location(
        "agent_monorepo",
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


load_source_package()

from agent_monorepo.events import EventHub
from agent_monorepo.memory.service import MemoryService
from agent_monorepo.resolver import ResolvedRunSpec
from agent_monorepo.runtime import AgentRuntime, RunContext
from agent_monorepo.strategy_feedback import (
    StrategyFeedbackCoordinator,
    fallback_analysis,
    parse_analysis,
)


class Registry:
    """Small registry substitute for feedback coordinator tests."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(tempfile.gettempdir())

    @property
    def project_config(self) -> dict:
        """Return a strategy-feedback enabled memory config."""
        return {
            "memory": {
                "enabled": True,
                "strategy_feedback": {
                    "enabled": True,
                    "feedback_timeout_seconds": 1,
                    "max_rework_cycles": 1,
                },
            }
        }

    @property
    def messaging_root(self) -> Path:
        """Return the feedback-test messaging root."""
        return self.root / ".agent-state" / "agents-messaging"


class StrategyFeedbackBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_analysis_accepts_fenced_json(self) -> None:
        parsed = parse_analysis(
            """```json
            {"feedback_type":"preference","rework":{"needed":false},"memory_actions":[]}
            ```"""
        )

        self.assertEqual("preference", parsed["feedback_type"])
        self.assertEqual([], parsed["memory_actions"])

    async def test_fallback_analysis_treats_requested_change_as_rework(self) -> None:
        analysis = fallback_analysis(
            {
                "status": "submitted",
                "store_work_memory": False,
                "feedback": "Looks close.",
                "requested_change": "Use a smaller UI.",
            }
        )

        self.assertEqual("rework_request", analysis["feedback_type"])
        self.assertTrue(analysis["rework"]["needed"])
        self.assertEqual([], analysis["memory_actions"])

    async def test_collect_feedback_uses_fixture_response_without_gui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / ".agent-state"
            fixture = root / "feedback.json"
            fixture.write_text(
                json.dumps(
                    {
                        "status": "submitted",
                        "store_work_memory": True,
                        "feedback": "Remember the rework loop.",
                        "requested_change": "",
                    }
                ),
                encoding="utf-8",
            )
            context = RunContext(
                run_id="run-feedback",
                session_id="session-feedback",
                prompt="Do the work",
                resolved=ResolvedRunSpec(
                    agent_id="agent-monorepo",
                    workflow_id="default",
                    skills=[],
                    tools=[],
                    needs_planning=False,
                    needs_web_search=False,
                    needs_ui=False,
                    context_queries=[],
                    validation_commands=[],
                ),
                project_root=root,
                agent_id="agent-monorepo",
                conditions={},
                event_hub=EventHub(state),
            )
            coordinator = StrategyFeedbackCoordinator(root, Registry(), object(), object())

            with patch.dict("os.environ", {"AGENT_STRATEGY_FEEDBACK_RESPONSE": str(fixture)}):
                result = await coordinator.collect_feedback(context)

            self.assertEqual("submitted", result["status"])
            self.assertTrue(Path(result["artifact_path"]).is_file())

    async def test_runtime_hook_stores_fallback_strategy_memory_when_analyzer_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / ".agent-state"
            events = EventHub(state)
            memory = MemoryService(
                state / "cache" / "memory",
                retrieval_enabled=True,
                extraction_enabled=True,
            )
            runtime = AgentRuntime(
                root,
                Registry(root),
                object(),
                events,
                memory,
                object(),
                object(),
            )
            context = RunContext(
                run_id="run-feedback",
                session_id="session-feedback",
                prompt="Do the work",
                resolved=ResolvedRunSpec(
                    agent_id="agent-monorepo",
                    workflow_id="default",
                    skills=[],
                    tools=[],
                    needs_planning=False,
                    needs_web_search=False,
                    needs_ui=False,
                    context_queries=[],
                    validation_commands=[],
                ),
                project_root=root,
                agent_id="agent-monorepo",
                conditions={},
                event_hub=events,
                memory_service=memory,
            )

            async def collect_feedback(_context: object) -> dict:
                return {
                    "status": "submitted",
                    "store_work_memory": True,
                    "feedback": "Remember that submitted post-work feedback must create durable strategy memory.",
                    "requested_change": "",
                }

            async def analyze_feedback(_context: object, _feedback: dict) -> dict:
                return {
                    "feedback_type": "preference",
                    "rework": {"needed": False, "prompt": ""},
                    "memory_actions": [],
                    "reason": "No durable analyzer action.",
                }

            runtime.strategy_feedback.collect_feedback = collect_feedback
            runtime.strategy_feedback.analyze_feedback = analyze_feedback

            result = await runtime._hook_step(
                {
                    "id": "store-strategy-memory",
                    "name": "Collect feedback and update strategy memory",
                    "hook": "strategy_memory_feedback",
                },
                context,
            )

            records = memory.load_records()
            updates = [
                event for event in events.load_run("run-feedback", "session-feedback")
                if event.type == "memory.updated"
            ]

            self.assertEqual({"hook": "strategy_memory_feedback", "status": "completed"}, result)
            self.assertEqual(1, len(records))
            self.assertEqual("active", records[0]["metadata"]["status"])
            self.assertTrue(context.data["strategy_memory_updates"][0]["fallback_used"])
            self.assertIn("submitted post-work feedback", memory.retrieve_context("post-work feedback memory"))
            self.assertEqual(1, updates[-1].payload["result"]["stored"])


if __name__ == "__main__":
    unittest.main()
