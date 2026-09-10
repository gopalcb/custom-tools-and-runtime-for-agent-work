from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


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
if str(ROOT / "agent-gateway") not in sys.path:
    sys.path.insert(0, str(ROOT / "agent-gateway"))

from agent_monorepo import bootstrap as bootstrap_module


class FakeCodexClient:
    """Deterministic in-memory substitute for the Codex App Server transport."""

    instances: list["FakeCodexClient"] = []

    def __init__(self, *_args, **kwargs) -> None:
        self.configuration = kwargs
        self.turns: list[dict[str, object]] = []
        self.interrupted = False
        self.closed = False
        self.instances.append(self)

    async def stream_turn(
        self,
        prompt: str,
        *,
        developer_instructions: str,
        model: str | None = None,
        thread_id: str | None = None,
    ):
        self.turns.append(
            {
                "prompt": prompt,
                "developer_instructions": developer_instructions,
                "model": model,
                "thread_id": thread_id,
            }
        )
        yield {
            "method": "client/thread",
            "params": {"threadId": "fake-thread", "turnId": "fake-turn"},
        }
        yield {"method": "item/agentMessage/delta", "params": {"delta": "Smoke "}}
        yield {"method": "item/agentMessage/delta", "params": {"delta": "complete"}}
        yield {
            "method": "item/completed",
            "params": {"item": {"type": "agentMessage", "text": "Smoke complete"}},
        }
        yield {
            "method": "item/commandExecution/outputDelta",
            "params": {"itemId": "command-1", "delta": "working\n"},
        }
        yield {
            "method": "thread/tokenUsage/updated",
            "params": {
                "tokenUsage": {
                    "total": {"inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
                    "last": {"inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
                    "modelContextWindow": 200000,
                }
            },
        }
        yield {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "fileChange",
                    "changes": [{"path": "generated/result.txt", "kind": "add"}],
                }
            },
        }
        yield {"method": "turn/diff/updated", "params": {"diff": "+Smoke complete\n"}}
        yield {
            "method": "turn/completed",
            "params": {"turn": {"id": "fake-turn", "status": "completed"}},
        }

    async def interrupt(self) -> None:
        self.interrupted = True

    async def close(self) -> None:
        self.closed = True


class FailingCodexClient(FakeCodexClient):
    async def stream_turn(self, *args, **kwargs):
        async for item in super().stream_turn(*args, **kwargs):
            yield item
            if item.get("method") == "client/thread":
                raise RuntimeError("synthetic transport failure")


class BlockingCodexClient(FakeCodexClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.started = asyncio.Event()

    async def stream_turn(self, prompt: str, **kwargs):
        self.turns.append({"prompt": prompt, **kwargs})
        yield {
            "method": "client/thread",
            "params": {"threadId": "fake-thread", "turnId": "blocking-turn"},
        }
        self.started.set()
        await asyncio.Event().wait()


class ApprovalCodexClient(FakeCodexClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.decision: asyncio.Future[str] | None = None

    async def stream_turn(self, prompt: str, **kwargs):
        self.turns.append({"prompt": prompt, **kwargs})
        yield {
            "method": "client/thread",
            "params": {"threadId": "fake-thread", "turnId": "approval-turn"},
        }
        self.decision = asyncio.get_running_loop().create_future()
        yield {
            "method": "client/approval/requested",
            "params": {
                "requestId": 77,
                "requestMethod": "item/fileChange/requestApproval",
                "approvalPolicy": "on-request",
                "status": "pending",
            },
        }
        await self.decision
        yield {"method": "item/agentMessage/delta", "params": {"delta": "Approved"}}
        yield {
            "method": "turn/completed",
            "params": {"turn": {"id": "approval-turn", "status": "completed"}},
        }

    async def respond_to_approval(self, request_id: int, decision: str) -> None:
        if request_id != 77 or self.decision is None:
            raise RuntimeError("unknown synthetic approval")
        self.decision.set_result(decision)


class FakeTransportIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary.name)
        self.validation_command = (
            f"{shlex.quote(sys.executable)} -c \"print('validation-ok')\""
        )
        self._write_project()
        FakeCodexClient.instances.clear()

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    def _write_yaml(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")

    def _write_project(self) -> None:
        (self.project_root / "agents" / "smoke-agent").mkdir(parents=True)
        (self.project_root / "agents" / "skills").mkdir(parents=True)
        (self.project_root / "agents" / "smoke-agent" / "instructions.md").write_text(
            "Return a deterministic smoke-test result.\n", encoding="utf-8"
        )
        self._write_yaml(
            self.project_root / "project-registry.yaml",
            {
                "version": 1,
                "paths": {
                    "agents": "agents",
                    "workflows": "agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml",
                    "state": ".agent-state",
                    "skills": "agents/skills",
                },
                "runtime": {
                    "default_agent": "smoke-agent",
                    "default_workflow": "smoke",
                    "max_parallel_tasks": 1,
                },
                "codex": {
                    "command": "codex app-server",
                    "supported_cli": ">=0.153.4,<0.154.0",
                    "working_directory": ".",
                    "approval_policy": "never",
                    "sandbox": "workspace-write",
                    "network_access": False,
                    "writable_roots": ["."],
                },
                "model_profiles": {"standard": None},
                "memory": {
                    "enabled": False,
                    "semantic_retrieval": False,
                    "extraction": False,
                },
                "validation": {"typecheck": self.validation_command},
            },
        )
        self._write_yaml(
            self.project_root
            / "agent-runtime"
            / "agent-monorepo"
            / "workflows"
            / "workflow-orchestrator.yaml",
            {
                "version": 1,
                "workflows": {
                    "smoke": {
                        "steps": [
                            {
                                "id": "context",
                                "name": "Resolve project context",
                                "uses": "tool",
                                "tool": "project_context",
                            },
                            {
                                "id": "execute",
                                "name": "Execute request",
                                "uses": "agent",
                                "agent": "$resolved_agent",
                                "depends_on": ["context"],
                            },
                            {
                                "id": "validate",
                                "name": "Validate result",
                                "uses": "shell",
                                "command": "$validation.typecheck",
                                "depends_on": ["execute"],
                            },
                            {
                                "id": "finalize",
                                "name": "Finalize result",
                                "uses": "hook",
                                "hook": "post_completion",
                                "depends_on": ["validate"],
                            },
                        ]
                    }
                },
            },
        )
        self._write_yaml(
            self.project_root / "agents" / "smoke-agent" / "agent.yaml",
            {
                "version": 1,
                "id": "smoke-agent",
                "name": "Smoke Agent",
                "instructions": "instructions.md",
                "workflow": "smoke",
                "skills": [],
                "tools": ["repo"],
                "model_profile": "standard",
            },
        )

    async def test_prompt_flows_through_runtime_and_creates_final_artifacts(self) -> None:
        session_id = "session-smoke"
        prompt = "Update the local smoke fixture"
        with patch.object(bootstrap_module, "CodexAppServerClient", FakeCodexClient):
            gateway = bootstrap_module.bootstrap(self.project_root)

        events = []
        try:
            async for runtime_event in gateway.run(prompt, session_id=session_id):
                events.append(runtime_event)
        finally:
            await gateway.close()

        self.assertEqual(1, len(FakeCodexClient.instances))
        client = FakeCodexClient.instances[0]
        self.assertTrue(client.closed)
        self.assertFalse(client.interrupted)
        self.assertEqual(1, len(client.turns))
        self.assertIn(prompt, str(client.turns[0]["prompt"]))
        self.assertIn("Allowed tools: repo", str(client.turns[0]["developer_instructions"]))

        event_types = [item.type for item in events]
        self.assertEqual("run.started", event_types[0])
        self.assertEqual("run.completed", event_types[-1])
        for expected in (
            "resolver.completed",
            "workflow.started",
            "agent.message.delta",
            "agent.message.completed",
            "agent.usage.updated",
            "file.changed",
            "artifact.created",
            "tool.progress",
            "tool.completed",
            "workflow.completed",
        ):
            self.assertIn(expected, event_types)
        self.assertEqual(
            "smoke",
            next(item for item in events if item.type == "resolver.completed").payload[
                "workflow_id"
            ],
        )
        self.assertEqual(
            "Smoke complete",
            "".join(
                item.message or ""
                for item in events
                if item.type == "agent.message.delta"
            ),
        )
        validation = next(
            item
            for item in events
            if item.type == "tool.completed" and item.payload.get("validation")
        )
        self.assertEqual(0, validation.payload["exit_code"])
        self.assertEqual("validation-ok", validation.payload["stdout"].strip())

        run_id = events[0].run_id
        run_dir = self.project_root / ".agent-state" / "logs" / session_id / run_id
        expected_files = {
            "artifacts.json",
            "events.jsonl",
            "memory_candidates.json",
            "metrics.json",
            "run.json",
            "summary.md",
        }
        self.assertEqual(expected_files, {path.name for path in run_dir.iterdir()})

        persisted_events = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        artifacts = json.loads(
            (run_dir / "artifacts.json").read_text(encoding="utf-8")
        )
        candidates = json.loads(
            (run_dir / "memory_candidates.json").read_text(encoding="utf-8")
        )
        session = json.loads(
            (
                self.project_root
                / ".agent-state"
                / "sessions"
                / session_id
                / "session.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual([item.to_dict() for item in events], persisted_events)
        self.assertEqual("completed", run["status"])
        self.assertEqual(len(events), run["event_count"])
        self.assertEqual(
            {"count": 1, "paths": ["generated/result.txt"]},
            metrics["file_changes"],
        )
        self.assertEqual("passed", metrics["validation"]["status"])
        self.assertEqual(
            [
                {"path": "generated/result.txt", "kind": "add"},
                {"path": "turn.diff", "kind": "diff"},
            ],
            [
                {"path": item["path"], "kind": item["kind"]}
                for item in artifacts["artifacts"]
            ],
        )
        self.assertEqual({"status": "disabled", "candidates": []}, candidates)
        self.assertEqual("completed", session["status"])
        self.assertEqual("fake-thread", session["codex_thread_id"])

    async def test_resume_reuses_the_persisted_codex_thread(self) -> None:
        with patch.object(bootstrap_module, "CodexAppServerClient", FakeCodexClient):
            gateway = bootstrap_module.bootstrap(self.project_root)
        try:
            first = [event async for event in gateway.run("First", session_id="session-resume")]
            second = [
                event
                async for event in gateway.run(
                    "Second", session_id="session-resume", resume=True
                )
            ]
        finally:
            await gateway.close()

        self.assertEqual("run.completed", first[-1].type)
        self.assertEqual("run.completed", second[-1].type)
        client = FakeCodexClient.instances[0]
        self.assertIsNone(client.turns[0]["thread_id"])
        self.assertEqual("fake-thread", client.turns[1]["thread_id"])

    async def test_cancel_interrupts_and_persists_cancelled_session(self) -> None:
        with patch.object(bootstrap_module, "CodexAppServerClient", BlockingCodexClient):
            gateway = bootstrap_module.bootstrap(self.project_root)
        client = FakeCodexClient.instances[0]
        events = []

        async def consume() -> None:
            async for event in gateway.run("Wait", session_id="session-cancel"):
                events.append(event)

        consumer = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(client.started.wait(), timeout=2)
            self.assertTrue(await gateway.cancel(events[0].run_id))
            await asyncio.wait_for(consumer, timeout=2)
        finally:
            if not consumer.done():
                consumer.cancel()
            await gateway.close()

        session = json.loads(
            (self.project_root / ".agent-state" / "sessions" / "session-cancel" / "session.json").read_text()
        )
        self.assertTrue(client.interrupted)
        self.assertIn("run.cancelled", [event.type for event in events])
        self.assertEqual("cancelled", session["status"])
        self.assertEqual("fake-thread", session["codex_thread_id"])

    async def test_transport_failure_persists_failed_session(self) -> None:
        with patch.object(bootstrap_module, "CodexAppServerClient", FailingCodexClient):
            gateway = bootstrap_module.bootstrap(self.project_root)
        try:
            events = [event async for event in gateway.run("Fail", session_id="session-failed")]
        finally:
            await gateway.close()

        session = json.loads(
            (self.project_root / ".agent-state" / "sessions" / "session-failed" / "session.json").read_text()
        )
        self.assertEqual("run.failed", events[-1].type)
        self.assertEqual("failed", session["status"])
        self.assertEqual("fake-thread", session["codex_thread_id"])
        self.assertIn("synthetic transport failure", session["error"])

    async def test_opt_in_approval_round_trips_through_public_gateway(self) -> None:
        config_path = self.project_root / "project-registry.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["codex"]["approval_policy"] = "on-request"
        self._write_yaml(config_path, config)
        with patch.object(bootstrap_module, "CodexAppServerClient", ApprovalCodexClient):
            gateway = bootstrap_module.bootstrap(self.project_root)

        events = []
        try:
            async for event in gateway.run("Approve", session_id="session-approval"):
                events.append(event)
                if event.payload.get("tool") == "approval":
                    self.assertEqual("pending", event.payload["status"])
                    await gateway.respond_to_approval(event.payload["request_id"], "accept")
        finally:
            await gateway.close()

        client = FakeCodexClient.instances[0]
        self.assertEqual("accept", client.decision.result())
        self.assertIn("Approved", "".join(event.message or "" for event in events))
        self.assertEqual("run.completed", events[-1].type)


if __name__ == "__main__":
    unittest.main()
