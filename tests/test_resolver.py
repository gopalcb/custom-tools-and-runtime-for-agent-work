from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_source_package() -> None:
    """Make the setuptools-mapped package importable without installing it."""
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

from agent_monorepo.registry import AgentDefinition, RegistryError
from agent_monorepo.resolver import (
    ResolutionError,
    Resolver,
    build_context_queries,
    collect_project_context,
    compact_context,
)


def _agent(
    agent_id: str,
    *,
    name: str,
    workflow: str = "default",
    aliases: tuple[str, ...] = (),
    skills: tuple[str, ...] = ("repository-navigation",),
    tools: tuple[str, ...] = ("repo", "web_search"),
) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        name=name,
        instructions_path=Path("instructions.md"),
        instructions="Follow the request.",
        workflow=workflow,
        skills=skills,
        skill_paths=tuple(Path(skill) / "SKILL.md" for skill in skills),
        tools=tools,
        aliases=aliases,
    )


class FakeRegistry:
    def __init__(self, *, default_agent: str | None = None) -> None:
        self.agents = {
            "agent-builder": _agent(
                "agent-builder",
                name="Agent Builder",
                workflow="build-agent",
                aliases=("builder",),
                skills=("agent-design", "agent-validation"),
            ),
            "agent-ui-builder": _agent(
                "agent-ui-builder",
                name="Agent UI Builder",
                aliases=("ui builder",),
                tools=("repo",),
            ),
            "agent-implementation-planner": _agent(
                "agent-implementation-planner", name="Implementation Planner Agent", aliases=("planner",)
            ),
        }
        runtime = {} if default_agent is None else {"default_agent": default_agent}
        self.project_config = {
            "runtime": runtime,
            "validation": {
                "agent": "validate-agent",
                "typecheck": ["compile", "shared"],
                "tests": ["shared", "test"],
            },
        }
        self.workflows = {
            "default": {
                "steps": [
                    {"id": "plan", "uses": "agent", "agent": "agent-implementation-planner", "when": "needs_planning"},
                    {"id": "run", "uses": "agent", "agent": "$resolved_agent"},
                ]
            },
            "build-agent": {
                "steps": [{"id": "plan", "uses": "agent", "agent": "agent-implementation-planner"}]
            },
        }

    def list_agents(self) -> list[AgentDefinition]:
        return [self.agents[key] for key in sorted(self.agents)]

    def get_agent(self, agent_id: str) -> AgentDefinition:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise RegistryError(f"Unknown agent '{agent_id}'") from exc

    def get_workflow(self, workflow_id: str) -> dict:
        try:
            return self.workflows[workflow_id]
        except KeyError as exc:
            raise RegistryError(f"Unknown workflow '{workflow_id}'") from exc


class ResolverBehaviorTests(unittest.TestCase):
    def test_explicit_agent_and_workflow_override_prompt_routing(self) -> None:
        resolver = Resolver(FakeRegistry())

        spec = resolver.resolve(
            "Create an agent UI and browse current framework docs",
            agent_id="agent-implementation-planner",
            workflow_id="default",
        )

        self.assertEqual("agent-implementation-planner", spec.agent_id)
        self.assertEqual("default", spec.workflow_id)
        self.assertFalse(spec.needs_planning)
        self.assertTrue(spec.needs_web_search)
        self.assertTrue(spec.needs_ui)
        self.assertIn("web_search", spec.tools)
        self.assertEqual(spec.conditions["needs_ui"], spec.needs_ui)

    def test_alias_and_specialized_prompt_routes_are_deterministic(self) -> None:
        resolver = Resolver(FakeRegistry())

        self.assertEqual("agent-builder", resolver.resolve("Builder: add a definition").agent_id)
        self.assertEqual("agent-builder", resolver.resolve("Scaffold a support agent").agent_id)
        self.assertEqual("agent-ui-builder", resolver.resolve("Create an HTML preview").agent_id)

    def test_flags_tools_skills_and_validation_follow_the_resolved_profile(self) -> None:
        resolver = Resolver(FakeRegistry())

        local = resolver.resolve("Fix a typo in local tests", agent_id="agent-builder")
        # The build-agent workflow explicitly requires its planner step.
        self.assertTrue(local.needs_planning)
        self.assertFalse(local.needs_web_search)
        self.assertNotIn("web_search", local.tools)
        self.assertEqual(["agent-design", "agent-validation"], local.skills)
        self.assertEqual(["validate-agent", "compile", "shared", "test"], local.validation_commands)

        trivial = resolver.resolve("Fix a typo in local tests", agent_id="agent-ui-builder")
        self.assertFalse(trivial.needs_planning)

        broad = resolver.resolve(
            "Refactor the gateway and update runtime tests across multiple subsystems",
            agent_id="agent-ui-builder",
        )
        self.assertTrue(broad.needs_planning)
        self.assertEqual(["compile", "shared", "test"], broad.validation_commands)

    def test_external_freshness_enables_web_but_local_facts_do_not(self) -> None:
        resolver = Resolver(FakeRegistry())

        external = resolver.resolve(
            "Check current SDK compatibility and official documentation",
            agent_id="agent-ui-builder",
        )
        local = resolver.resolve(
            "Show this repository structure and existing local behavior",
            agent_id="agent-ui-builder",
        )

        self.assertTrue(external.needs_web_search)
        self.assertIn("web_search", external.tools)
        self.assertFalse(local.needs_web_search)
        self.assertNotIn("web_search", local.tools)

    def test_context_queries_are_bounded_stable_and_deduplicated(self) -> None:
        queries = build_context_queries(
            "Update `Resolver` in agent-runtime/agent-monorepo/resolver.py; resolver Resolver",
            agent_id="agent-builder",
            workflow_id="build-agent",
            skills=("agent-design",),
            max_queries=6,
        )

        self.assertLessEqual(len(queries), 6)
        self.assertEqual(len(queries), len({query.casefold() for query in queries}))
        self.assertEqual("agent-runtime/agent-monorepo/resolver.py", queries[0])
        self.assertIn("Resolver", queries)

    def test_context_collection_stays_in_configured_roots_and_compacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "other").mkdir()
            (root / "src" / "match.py").write_text("needle in allowed source", encoding="utf-8")
            (root / "other" / "match.py").write_text("needle outside root", encoding="utf-8")

            items = asyncio.run(
                collect_project_context(root, ["needle"], configured_roots=["src"])
            )
            rendered = compact_context(items, max_chars=45, per_file_chars=100)

        self.assertEqual(["src/match.py"], [item.path for item in items])
        self.assertLessEqual(len(rendered), 45)
        self.assertIn("src/match.py", rendered)
        self.assertNotIn("outside root", rendered)

    def test_invalid_requests_and_configuration_fail_clearly(self) -> None:
        registry = FakeRegistry()
        resolver = Resolver(registry)

        with self.assertRaisesRegex(ResolutionError, "non-empty"):
            resolver.resolve(" ")
        with self.assertRaisesRegex(ResolutionError, "Unknown agent"):
            resolver.resolve("work", agent_id="missing")
        with self.assertRaisesRegex(ResolutionError, "Unknown workflow"):
            resolver.resolve("work", agent_id="agent-builder", workflow_id="missing")
        with self.assertRaisesRegex(ResolutionError, "Unable to select"):
            resolver.resolve("Handle the request")

        registry.project_config["validation"] = "invalid"
        with self.assertRaisesRegex(ResolutionError, "must be a mapping"):
            resolver.resolve("work", agent_id="agent-ui-builder")


if __name__ == "__main__":
    unittest.main()
