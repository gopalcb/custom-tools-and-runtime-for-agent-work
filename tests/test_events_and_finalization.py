from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_source_package() -> None:
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


_load_source_package()

from agent_monorepo.events import EventHub
from agent_monorepo.memory.service import MemoryService
from agent_monorepo.post_completion import finalize_run


class EventHubBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.hub = EventHub(self.temporary.name)

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    def event(self, event_type: str = "run.started", **values):
        return self.hub.new_event(
            event_type,
            run_id=values.pop("run_id", "run-1"),
            session_id=values.pop("session_id", "session-1"),
            **values,
        )

    async def test_emit_is_immediately_durable_and_delivers_same_event_in_order(self) -> None:
        subscriber = self.hub.subscribe("run-1", session_id="session-1")
        unrelated = self.hub.subscribe("other-run")

        emitted = await asyncio.gather(
            *(self.hub.emit(self.event(message=f"event-{number}")) for number in range(8))
        )
        path = self.hub.run_dir("session-1", "run-1") / "events.jsonl"
        on_disk = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        delivered = [await subscriber.get() for _ in emitted]
        emitted_by_seq = {event.seq: event for event in emitted}

        self.assertEqual(list(range(1, 9)), [item["seq"] for item in on_disk])
        self.assertEqual(on_disk, [event.to_dict() for event in delivered])
        self.assertTrue(all(event is emitted_by_seq[event.seq] for event in delivered))
        self.assertTrue(unrelated.empty())

        self.hub.unsubscribe(subscriber)
        await self.hub.emit(self.event(message="after unsubscribe"))
        self.assertTrue(subscriber.empty())

    async def test_reload_preserves_partial_history_and_ignores_only_a_torn_tail(self) -> None:
        await self.hub.emit(self.event("run.started"))
        await self.hub.emit(self.event("workflow.started"))
        path = self.hub.run_dir("session-1", "run-1") / "events.jsonl"
        with path.open("ab") as handle:
            handle.write(b'{"seq":3,"type":"workflow.step')
            handle.flush()

        restarted = EventHub(self.temporary.name)
        loaded = restarted.load_run("run-1", "session-1")

        self.assertEqual([1, 2], [event.seq for event in loaded])
        self.assertEqual(["run.started", "workflow.started"], [event.type for event in loaded])

    async def test_sequence_continues_after_process_restart(self) -> None:
        await self.hub.emit(self.event("run.started"))
        restarted = EventHub(self.temporary.name)
        emitted = await restarted.emit(self.event("run.completed"))
        self.assertEqual(2, emitted.seq)


class FinalizationBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.hub = EventHub(self.temporary.name)
        self.memory = MemoryService(Path(self.temporary.name) / "memory")

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    async def emit(self, event_type: str, ts: str, **values) -> None:
        await self.hub.emit(
            self.hub.new_event(
                event_type,
                run_id="run-final",
                session_id="session-final",
                ts=ts,
                **values,
            )
        )

    async def test_final_artifacts_metrics_summary_and_disabled_memory_derive_from_events(self) -> None:
        await self.emit("run.started", "2026-01-01T00:00:00Z", agent_id="agent-builder")
        await self.emit("workflow.step.started", "2026-01-01T00:00:01Z", step_id="validate")
        await self.emit("workflow.step.failed", "2026-01-01T00:00:02Z", step_id="validate")
        await self.emit("workflow.step.started", "2026-01-01T00:00:03Z", step_id="validate")
        await self.emit("tool.started", "2026-01-01T00:00:04Z", payload={"tool": "shell", "validation": True})
        await self.emit("tool.completed", "2026-01-01T00:00:06Z", payload={"tool": "shell", "validation": True})
        await self.emit("workflow.step.completed", "2026-01-01T00:00:07Z", step_id="validate")
        await self.emit("file.changed", "2026-01-01T00:00:08Z", payload={"path": "src/app.py"})
        await self.emit("file.changed", "2026-01-01T00:00:09Z", payload={"path": "src/app.py"})
        await self.emit(
            "artifact.created",
            "2026-01-01T00:00:10Z",
            payload={"path": "dist/report.json", "kind": "report", "size": 42},
        )
        await self.emit("background.started", "2026-01-01T00:00:11Z", payload={"task_id": "index"})
        await self.emit("background.completed", "2026-01-01T00:00:12Z", payload={"task_id": "index"})
        await self.emit("run.completed", "2026-01-01T00:00:15Z", message="Everything passed")

        paths = finalize_run(self.hub, self.memory, "session-final", "run-final")
        run = json.loads(paths.run.read_text(encoding="utf-8"))
        metrics = json.loads(paths.metrics.read_text(encoding="utf-8"))
        artifacts = json.loads(paths.artifacts.read_text(encoding="utf-8"))
        candidates = json.loads(paths.memory_candidates.read_text(encoding="utf-8"))
        summary = paths.summary.read_text(encoding="utf-8")

        self.assertEqual("completed", run["status"])
        self.assertEqual(15.0, run["duration_seconds"])
        self.assertEqual(13, run["event_count"])
        self.assertEqual(1, metrics["retries"])
        self.assertEqual({"calls": 1, "completed": 1, "failed": 0}, metrics["tools"])
        self.assertEqual({"count": 1, "paths": ["src/app.py"]}, metrics["file_changes"])
        self.assertEqual({"count": 1, "completed": 1, "failed": 0}, metrics["background_tasks"])
        self.assertEqual(2.0, metrics["tool_durations_seconds"]["shell"])
        self.assertEqual(1.0, metrics["background_durations_seconds"]["index"])
        self.assertEqual("passed", metrics["validation"]["status"])
        self.assertEqual(
            [{
                "path": "dist/report.json",
                "kind": "report",
                "created_at": "2026-01-01T00:00:10Z",
                "seq": 10,
                "size": 42,
            }],
            artifacts["artifacts"],
        )
        self.assertEqual({"status": "disabled", "candidates": []}, candidates)
        self.assertIn("# Run run-final", summary)
        self.assertIn("Status: completed", summary)
        self.assertIn("Everything passed", summary)

    async def test_finalization_requires_persisted_events(self) -> None:
        with self.assertRaisesRegex(ValueError, "no persisted events"):
            finalize_run(self.hub, self.memory, "session-final", "empty-run")

    async def test_enabled_memory_candidates_are_stored_and_retrievable(self) -> None:
        memory = MemoryService(
            Path(self.temporary.name) / "memory-enabled",
            retrieval_enabled=True,
            extraction_enabled=True,
        )
        await self.emit(
            "run.started",
            "2026-01-01T00:00:00Z",
            agent_id="codex-agent",
            message="Fix unsupported Codex CLI 0.154.0 planning failure",
        )
        await self.emit(
            "resolver.completed",
            "2026-01-01T00:00:01Z",
            agent_id="codex-agent",
            payload={"agent_id": "codex-agent", "workflow_id": "default"},
        )
        await self.emit(
            "workflow.step.failed",
            "2026-01-01T00:00:02Z",
            agent_id="codex-agent",
            step_id="plan",
            message="Unsupported Codex CLI 0.154.0; supported range is >=0.153.4,<0.154.0.",
        )
        await self.emit(
            "error",
            "2026-01-01T00:00:03Z",
            agent_id="codex-agent",
            message="Unsupported Codex CLI 0.154.0; supported range is >=0.153.4,<0.154.0.",
        )
        await self.emit(
            "run.failed",
            "2026-01-01T00:00:04Z",
            agent_id="codex-agent",
            message="Unsupported Codex CLI 0.154.0; supported range is >=0.153.4,<0.154.0.",
        )

        paths = finalize_run(self.hub, memory, "session-final", "run-final")
        candidates = json.loads(paths.memory_candidates.read_text(encoding="utf-8"))
        records = memory.load_records()
        context = memory.retrieve_context("Codex CLI 0.154.0 planning failure")

        self.assertEqual("ready", candidates["status"])
        self.assertGreaterEqual(len(candidates["candidates"]), 2)
        self.assertEqual(
            set(candidates["stored_records"]),
            {record["path"] for record in records},
        )
        self.assertIn("Unsupported Codex CLI 0.154.0", context)

    async def test_strategy_memory_actions_store_and_supersede_active_records(self) -> None:
        memory = MemoryService(
            Path(self.temporary.name) / "strategy-memory",
            retrieval_enabled=True,
            extraction_enabled=True,
        )
        source = {
            "session_id": "session-final",
            "run_id": "run-final",
            "created_at": "2026-01-01T00:00:05Z",
            "scope": {
                "repo": "agent-monorepo",
                "agent_id": "agent-monorepo",
                "workflow_id": "default",
            },
        }

        first = memory.apply_strategy_memory_actions(
            [
                {
                    "action": "add",
                    "kind": "user-work-strategy",
                    "subject": "Manual testing feedback",
                    "content": "The user prefers manual testing gaps to become a rework loop before the final answer.",
                    "confidence": 0.9,
                }
            ],
            source,
        )
        second = memory.apply_strategy_memory_actions(
            [
                {
                    "action": "update",
                    "kind": "user-work-strategy",
                    "subject": "Manual testing feedback",
                    "content": "The user prefers manual testing feedback to trigger rework and another feedback request before finalization.",
                    "confidence": 0.95,
                }
            ],
            {**source, "created_at": "2026-01-01T00:01:00Z"},
        )

        records = memory.load_records()
        active = [
            record for record in records
            if record["metadata"].get("kind") == "user-work-strategy"
            and record["metadata"].get("status") == "active"
        ]
        superseded = [
            record for record in records
            if record["metadata"].get("kind") == "user-work-strategy"
            and record["metadata"].get("status") == "superseded"
        ]
        context = memory.retrieve_context("manual testing feedback rework finalization")

        self.assertEqual(1, first["stored"])
        self.assertEqual(1, second["stored"])
        self.assertEqual(1, len(active))
        self.assertEqual(1, len(superseded))
        self.assertIn("another feedback request", context)
        self.assertNotIn("before the final answer", context)


if __name__ == "__main__":
    unittest.main()
