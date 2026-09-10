from __future__ import annotations

import unittest
from pathlib import Path

from agent_monorepo.registry import Registry
from agent_monorepo.resolver import Resolver


ROOT = Path(__file__).resolve().parents[1]


class DefaultConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Registry(ROOT)
        self.resolver = Resolver(self.registry)

    def test_unqualified_prompt_starts_planning_before_the_smoke_workflow(self) -> None:
        resolved = self.resolver.resolve("Check runtime")

        self.assertEqual("codex-agent", resolved.agent_id)
        self.assertEqual("codex-smoke", resolved.workflow_id)
        self.assertEqual("workflow-selection", resolved.planning_workflow_id)
        self.assertEqual(
            ["analyze", "resolve-context", "web-research", "plan"],
            [step["id"] for step in self.registry.get_workflow("workflow-selection")["steps"]],
        )

    def test_explicit_specialized_agent_still_selects_its_own_workflow(self) -> None:
        resolved = self.resolver.resolve("Create an HTML preview")

        self.assertEqual("agent-ui-builder", resolved.agent_id)
        self.assertEqual("default", resolved.workflow_id)


if __name__ == "__main__":
    unittest.main()
