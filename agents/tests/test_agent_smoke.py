from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_builder.models import AgentBuildRequest
from agent_builder.service import AgentBuilderService
from agent_gateway import AgentGateway
from agent_gateway.models import AgentSpec, LoadedAgent, RuntimeConfig
from agent_gateway.providers.codex import CodexProvider


REPO_ROOT = Path(__file__).resolve().parents[2]


class AgentGatewaySmokeTests(unittest.TestCase):
    def test_registered_agents_are_loadable_and_valid(self) -> None:
        gateway = AgentGateway(REPO_ROOT)

        self.assertEqual(gateway.list_agents(), ["agent-builder", "agent-ui-builder"])

        for agent_id in gateway.list_agents():
            loaded = gateway.load(agent_id)
            self.assertEqual(loaded.spec.id, agent_id)
            self.assertTrue(loaded.instructions.strip())
            self.assertTrue(loaded.skills)
            self.assertIsInstance(loaded.evaluations, dict)
            self.assertEqual(gateway.validate(agent_id).id, agent_id)

    def test_codex_provider_reports_startup_failure_as_run_result(self) -> None:
        agent = LoadedAgent(
            spec=AgentSpec(
                id="agent-runtime-test",
                description="Runtime test agent",
                purpose="Exercise runtime provider failure handling",
                runtime=RuntimeConfig(provider="codex"),
            ),
            root=REPO_ROOT / "agents",
            instructions="Test instructions",
        )

        with patch.object(CodexProvider, "_sdk", side_effect=RuntimeError("missing codex sdk")):
            result = CodexProvider().run_new(agent, "hello", cwd=REPO_ROOT / "agents")

        self.assertEqual(result.agent_id, "agent-runtime-test")
        self.assertEqual(result.status, "failed")
        self.assertIn("missing codex sdk", result.error or "")


class AgentBuilderSmokeTests(unittest.TestCase):
    def make_service(self, temp_root: Path) -> AgentBuilderService:
        agents_root = temp_root / "agents"
        agents_root.mkdir()
        shutil.copytree(REPO_ROOT / "agents" / "agent-builder", agents_root / "agent-builder")
        return AgentBuilderService(temp_root)

    def test_preview_does_not_write_and_build_creates_loadable_agent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-builder-test-") as raw_root:
            temp_root = Path(raw_root)
            service = self.make_service(temp_root)
            request = AgentBuildRequest(
                name="Code Review",
                purpose="Review agent folders and validate changes",
            )

            preview = service.preview(request)

            self.assertEqual(preview.agent_id, "agent-code-review")
            self.assertFalse((temp_root / "agents" / preview.agent_id).exists())

            result = service.build(request)

            self.assertEqual(result.agent_id, preview.agent_id)
            self.assertEqual(result.created_files, ["agent.yaml", "AGENT.md", "skills.yaml", "evals.yaml"])
            loaded = service.gateway.load(preview.agent_id)
            self.assertEqual(loaded.spec.id, preview.agent_id)
            self.assertIn("repository-navigation", loaded.skills)
            self.assertTrue(loaded.instructions.strip())
            self.assertIn("quality", loaded.evaluations)

    def test_build_refuses_existing_agent_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-builder-test-") as raw_root:
            service = self.make_service(Path(raw_root))
            request = AgentBuildRequest(
                name="Code Review",
                purpose="Review agent folders and validate changes",
            )

            service.build(request)

            with self.assertRaises(FileExistsError):
                service.build(request)


class AgentRuntimeResolverSmokeTests(unittest.TestCase):
    def test_project_registry_resolves_enabled_agents(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "agents" / "agent-runtime" / "agent-monorepo"))
        from bootstrap import load_registry
        from resolver import resolve_project

        registry = load_registry(REPO_ROOT)

        self.assertEqual(
            resolve_project("please use the agent builder", registry).project,
            "agent-builder",
        )
        self.assertEqual(
            resolve_project("make an interface mockup", registry).project,
            "agent-ui-builder",
        )


if __name__ == "__main__":
    unittest.main()
