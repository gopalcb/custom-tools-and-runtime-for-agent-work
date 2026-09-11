"""Resolve prompts into validated agent, workflow, and context specifications."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .registry import AgentDefinition, Registry, RegistryError


class ResolutionError(ValueError):
    """Raised when a request cannot be resolved deterministically."""


@dataclass
class ResolvedRunSpec:
    agent_id: str
    workflow_id: str
    skills: list[str]
    tools: list[str]
    needs_planning: bool
    needs_web_search: bool
    needs_ui: bool
    context_queries: list[str]
    validation_commands: list[str]
    conditions: dict[str, bool] = field(default_factory=dict)
    planning_workflow_id: str | None = None


@dataclass(frozen=True)
class ContextItem:
    path: str
    content: str
    score: int
    source_priority: int


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{1,79}")
_PATH = re.compile(r"(?<!\w)(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_STOP_WORDS = frozenset(
    {
        "about", "after", "again", "also", "and", "before", "build", "change",
        "check", "code", "create", "file", "from", "have", "implement", "into",
        "make", "need", "please", "project", "repository", "should", "task", "that",
        "the", "then", "this", "use", "using", "want", "with", "work",
    }
)

_AGENT_BUILDING = re.compile(
    r"\b(?:build|create|design|scaffold|generate|add)\b.{0,32}\bagent\b|"
    r"\bagent\b.{0,24}\b(?:builder|definition|instructions|skill)\b",
    re.IGNORECASE,
)
_UI_REQUEST = re.compile(
    r"\b(?:ui|ux|user interface|mock-?up|wireframe|html|css|frontend|preview)\b",
    re.IGNORECASE,
)
_EXPLICIT_WEB = re.compile(
    r"\b(?:browse|web search|search (?:the )?(?:web|internet)|research online|"
    r"look (?:it|this|that) up)\b",
    re.IGNORECASE,
)
_FRESHNESS = re.compile(
    r"\b(?:latest|current(?:ly)?|up[- ]to[- ]date|today|recent)\b",
    re.IGNORECASE,
)
_EXTERNAL_BEHAVIOR = re.compile(
    r"\b(?:compatib(?:le|ility)|release notes?|changelog|upgrade|deprecat(?:ed|ion)|"
    r"breaking changes?|official (?:docs?|documentation|specification)|"
    r"third[- ]party|framework|library|sdk|api version|package version|"
    r"npm|pypi|crates\.io)\b",
    re.IGNORECASE,
)
_LOCAL_FACT = re.compile(
    r"\b(?:repository (?:structure|tree)|local (?:code|behavior|tests?)|"
    r"project conventions?|existing (?:source|config|docs?)|this (?:repo|repository))\b",
    re.IGNORECASE,
)
_PLANNING = re.compile(
    r"\b(?:plan|architecture|architect|migration|migrate|refactor|redesign|"
    r"across|end[- ]to[- ]end|multiple (?:modules|packages|services|subsystems))\b",
    re.IGNORECASE,
)
_SKIP_PLANNING = re.compile(
    r"\b(?:skip|without|no|do not|don't)\b.{0,24}\b(?:planning|planner|plan workflow|workflow-selection)\b|"
    r"\b(?:planning|planner|plan workflow|workflow-selection)\b.{0,24}\b(?:skip|off|disabled)\b",
    re.IGNORECASE,
)
_TRIVIAL = re.compile(
    r"\b(?:typo|spelling|rename|one[- ]line|single (?:line|file)|explain|show|list)\b",
    re.IGNORECASE,
)
_DIAG_BUILDER_PREFIX = re.compile(r"^\s*/diag-builder(?:\s|$)", re.IGNORECASE)
_DIAGRAM_HTML_REQUEST = re.compile(
    r"\b(?:(?:use|using)\s+diagram\s+builder|(?:create|build|render|generate|make)\s+"
    r"(?:an?\s+)?(?:html\s+)?(?:architecture\s+|runtime\s+|flow\s+|tree\s+)?diagram|"
    r"diagram\s+(?:as|in|to)\s+(?:html|html file)|html\s+diagram)\b",
    re.IGNORECASE,
)
_MARKDOWN_DOCUMENT_REQUEST = re.compile(
    r"(?:\b(?:markdown|md)\b|\.md\b|README\.md\b|"
    r"\b(?:save|write|store|create)\b.{0,40}\b(?:document|article|post|file)\b.{0,20}\b(?:markdown|md)\b|"
    r"\b(?:save|write|store|create)\b.{0,40}\.md\b)",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


class Resolver:
    """Turn a prompt into one deterministic, non-executing run specification."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def resolve(
        self,
        prompt: str,
        *,
        agent_id: str | None = None,
        workflow_id: str | None = None,
    ) -> ResolvedRunSpec:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ResolutionError("Prompt must be a non-empty string")

        selected = self._select_agent(prompt, agent_id)
        selected_workflow = workflow_id or selected.workflow
        try:
            workflow = self.registry.get_workflow(selected_workflow)
        except RegistryError as exc:
            raise ResolutionError(str(exc)) from exc

        needs_ui = self._needs_ui(prompt)
        needs_web = self._needs_web_search(prompt)
        needs_planning = self._needs_planning(prompt, selected, workflow)
        skip_planning = self.skips_planning(prompt)
        if workflow_id is None and needs_planning and selected_workflow == "codex-smoke":
            selected_workflow = "default"
            try:
                workflow = self.registry.get_workflow(selected_workflow)
            except RegistryError as exc:
                raise ResolutionError(str(exc)) from exc
        tools = list(selected.tools)
        if needs_web and "web_search" not in tools:
            tools.append("web_search")
        elif not needs_web:
            tools = [tool for tool in tools if tool != "web_search"]

        validation_commands = self._validation_commands(selected_workflow)
        queries = build_context_queries(
            prompt,
            agent_id=selected.id,
            workflow_id=selected_workflow,
            skills=selected.skills,
        )
        conditions = {
            "needs_planning": needs_planning,
            "needs_web_search": needs_web,
            "needs_ui": needs_ui,
            "skip_planning": skip_planning,
        }
        planning_workflow_id: str | None = None
        if not skip_planning:
            try:
                planning_workflow = self.registry.get_workflow("workflow-selection")
                if planning_workflow.get("phase") == "planning":
                    planning_workflow_id = "workflow-selection"
            except RegistryError:
                pass
        logger.info(
            "Prompt resolved",
            extra={
                "agent_id": selected.id,
                "workflow_id": selected_workflow,
                "needs_planning": needs_planning,
                "needs_web_search": needs_web,
                "needs_ui": needs_ui,
            },
        )
        return ResolvedRunSpec(
            agent_id=selected.id,
            workflow_id=selected_workflow,
            skills=list(selected.skills),
            tools=tools,
            needs_planning=needs_planning,
            needs_web_search=needs_web,
            needs_ui=needs_ui,
            context_queries=queries,
            validation_commands=validation_commands,
            conditions=conditions,
            planning_workflow_id=planning_workflow_id,
        )

    def _select_agent(self, prompt: str, requested: str | None) -> AgentDefinition:
        agents = self.registry.list_agents()
        if requested:
            try:
                return self.registry.get_agent(requested)
            except RegistryError as exc:
                raise ResolutionError(str(exc)) from exc

        normalized = " ".join(prompt.casefold().split())
        markdown_document = self._is_markdown_document_request(prompt)
        if self._needs_html_diagram(prompt):
            return self._required_agent("diagram-builder", "HTML diagram request")
        for agent in agents:
            if markdown_document and agent.id == "diagram-builder":
                continue
            if _contains_phrase(normalized, agent.id.casefold()):
                return agent
        for agent in agents:
            if markdown_document and agent.id == "diagram-builder":
                continue
            aliases = (agent.name, *agent.aliases)
            if agent.id == "agent-implementation-planner" and not normalized.startswith(
                ("planner", "plan work", "implementation planner")
            ):
                continue
            if any(_contains_phrase(normalized, alias.casefold()) for alias in aliases):
                return agent

        if _AGENT_BUILDING.search(prompt):
            return self._required_agent("agent-builder", "agent-building request")
        if self._needs_ui(prompt):
            return self._required_agent("agent-ui-builder", "UI request")

        runtime = self.registry.project_config.get("runtime", {})
        default_agent = runtime.get("default_agent")
        if default_agent:
            return self._required_agent(default_agent, "configured default")

        executable = [
            agent
            for agent in agents
            if agent.id != "agent-implementation-planner"
        ]
        if len(executable) == 1:
            return executable[0]
        available = ", ".join(agent.id for agent in agents)
        raise ResolutionError(
            "Unable to select an agent deterministically. Specify an agent id or alias; "
            f"available agents: {available}"
        )

    def _required_agent(self, agent_id: str, reason: str) -> AgentDefinition:
        try:
            return self.registry.get_agent(agent_id)
        except RegistryError as exc:
            raise ResolutionError(f"Cannot handle {reason}: {exc}") from exc

    @staticmethod
    def _needs_ui(prompt: str) -> bool:
        return bool(_UI_REQUEST.search(prompt))

    @staticmethod
    def _needs_web_search(prompt: str) -> bool:
        if _EXPLICIT_WEB.search(prompt):
            return True
        local_fact = bool(_LOCAL_FACT.search(prompt))
        external_fact = bool(_EXTERNAL_BEHAVIOR.search(prompt))
        if local_fact and not external_fact:
            return False
        return external_fact or bool(_FRESHNESS.search(prompt))

    @staticmethod
    def _needs_planning(
        prompt: str,
        selected: AgentDefinition,
        workflow: Mapping[str, Any],
    ) -> bool:
        if selected.id == "agent-implementation-planner":
            return False
        for step in _walk_steps(workflow.get("steps", [])):
            if step.get("uses") == "agent" and step.get("agent") == "agent-implementation-planner":
                condition = step.get("when")
                if condition is None or condition is True:
                    return True
        if _TRIVIAL.search(prompt) and not _PLANNING.search(prompt):
            return False
        if _PLANNING.search(prompt):
            return True
        action_count = len(
            re.findall(
                r"\b(?:add|build|change|create|implement|integrate|migrate|refactor|remove|update)\b",
                prompt,
                re.IGNORECASE,
            )
        )
        subsystem_count = len(
            set(
                re.findall(
                    r"\b(?:api|backend|cli|console|database|frontend|gateway|memory|"
                    r"registry|resolver|runtime|tests?|ui|workflow)\b",
                    prompt.casefold(),
                )
            )
        )
        return action_count >= 2 and subsystem_count >= 2

    @staticmethod
    def skips_planning(prompt: str) -> bool:
        """Return whether the user explicitly asked to bypass planning."""
        return bool(_SKIP_PLANNING.search(prompt))

    @staticmethod
    def _needs_html_diagram(prompt: str) -> bool:
        """Return whether the prompt should route to the HTML diagram builder."""
        if Resolver._is_markdown_document_request(prompt):
            return False
        return bool(_DIAG_BUILDER_PREFIX.search(prompt) or _DIAGRAM_HTML_REQUEST.search(prompt))

    @staticmethod
    def _is_markdown_document_request(prompt: str) -> bool:
        """Return whether the prompt asks for a Markdown document artifact."""
        return bool(_MARKDOWN_DOCUMENT_REQUEST.search(prompt))

    def _validation_commands(self, workflow_id: str) -> list[str]:
        validation = self.registry.project_config.get("validation", {})
        if not isinstance(validation, dict):
            raise ResolutionError("Project validation configuration must be a mapping")
        ordered_keys = (
            ("agent", "typecheck", "tests")
            if workflow_id == "build-agent"
            else ("typecheck", "tests")
        )
        commands: list[str] = []
        for key in ordered_keys:
            value = validation.get(key)
            if isinstance(value, str) and value.strip() and value not in commands:
                commands.append(value)
            elif isinstance(value, list):
                commands.extend(
                    command for command in value if isinstance(command, str) and command and command not in commands
                )
        return commands


def build_context_queries(
    prompt: str,
    *,
    agent_id: str | None = None,
    workflow_id: str | None = None,
    skills: Sequence[str] = (),
    max_queries: int = 8,
) -> list[str]:
    """Build a small stable set of literal terms for repository retrieval."""
    if max_queries < 1:
        return []
    candidates: list[str] = []
    candidates.extend(_PATH.findall(prompt))
    candidates.extend(match.group(1) for match in re.finditer(r"`([^`\n]+)`", prompt))
    candidates.extend(
        word
        for word in _WORD.findall(prompt)
        if word.casefold() not in _STOP_WORDS and len(word) >= 3
    )
    if agent_id:
        candidates.append(agent_id)
    if workflow_id:
        candidates.append(workflow_id)
    candidates.extend(skills)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = " ".join(candidate.strip().split())[:120]
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) == max_queries:
            break
    return result


async def collect_project_context(
    project_root: str | Path,
    queries: Sequence[str],
    *,
    configured_roots: Sequence[str | Path] | None = None,
    max_files: int = 20,
    max_chars: int = 40_000,
    max_file_bytes: int = 512_000,
) -> list[ContextItem]:
    """Search allowed repository roots without crossing the project boundary."""
    items = await asyncio.to_thread(
        _collect_project_context,
        Path(project_root),
        tuple(queries),
        configured_roots,
        max_files,
        max_chars,
        max_file_bytes,
    )
    logger.info(
        "Project context collected",
        extra={"project_root": str(project_root), "query_count": len(queries), "file_count": len(items)},
    )
    return items


def compact_context(
    items: Sequence[ContextItem | Mapping[str, Any] | str],
    *,
    max_chars: int = 24_000,
    per_file_chars: int = 8_000,
) -> str:
    """Render retrieved context into a bounded, source-labelled text block."""
    if max_chars <= 0 or per_file_chars <= 0:
        return ""
    chunks: list[str] = []
    used = 0
    for index, item in enumerate(items):
        if isinstance(item, ContextItem):
            path, content = item.path, item.content
        elif isinstance(item, Mapping):
            path = str(item.get("path", f"context-{index + 1}"))
            content = str(item.get("content", ""))
        else:
            path, content = f"context-{index + 1}", str(item)
        content = content[:per_file_chars]
        chunk = f"### {path}\n{content.rstrip()}\n"
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            marker = "\n[context truncated]"
            chunks.append(chunk[: max(0, remaining - len(marker))] + marker)
            used = max_chars
            break
        chunks.append(chunk)
        used += len(chunk)
    return "\n".join(chunks)


def _collect_project_context(
    project_root: Path,
    queries: tuple[str, ...],
    configured_roots: Sequence[str | Path] | None,
    max_files: int,
    max_chars: int,
    max_file_bytes: int,
) -> list[ContextItem]:
    project_root = project_root.resolve()
    if not project_root.is_dir():
        raise ResolutionError(f"Project root does not exist: {project_root}")
    if max_files < 1 or max_chars < 1 or max_file_bytes < 1:
        return []

    defaults: tuple[str, ...] = (
        "agent-config/context",
        "agent-config/agents",
        "agent-config/skills",
        "agent-runtime",
        "agent-gateway",
        "tests",
        "project-registry.yaml",
        "pyproject.toml",
        "docs",
    )
    roots = configured_roots or defaults
    allowed: list[Path] = []
    for value in roots:
        raw = Path(value)
        path = raw.resolve() if raw.is_absolute() else (project_root / raw).resolve()
        try:
            path.relative_to(project_root)
        except ValueError as exc:
            raise ResolutionError(f"Context root escapes project root: {value}") from exc
        if path.exists() and path not in allowed:
            allowed.append(path)

    normalized_queries = tuple(query.casefold() for query in queries if query.strip())
    candidates: list[ContextItem] = []
    seen_paths: set[Path] = set()
    scanned = 0
    for root in allowed:
        paths: Iterable[Path] = (root,) if root.is_file() else root.rglob("*")
        for path in paths:
            if scanned >= 4_000:
                break
            if not path.is_file() or path.is_symlink() or _ignored_path(path, project_root):
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                raw = path.read_bytes()
            except OSError:
                continue
            scanned += 1
            if b"\0" in raw[:4096]:
                continue
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            relative = path.relative_to(project_root).as_posix()
            source_priority = _source_priority(relative)
            haystack_path = relative.casefold()
            haystack_content = content.casefold()
            if normalized_queries:
                path_hits = sum(query in haystack_path for query in normalized_queries)
                content_hits = sum(query in haystack_content for query in normalized_queries)
                if not path_hits and not content_hits:
                    continue
            else:
                path_hits = content_hits = 0
            score = (path_hits * 20) + (content_hits * 5) + max(0, 10 - source_priority)
            candidates.append(
                ContextItem(
                    path=relative,
                    content=content,
                    score=score,
                    source_priority=source_priority,
                )
            )

    candidates.sort(key=lambda item: (-item.score, item.source_priority, item.path))
    selected: list[ContextItem] = []
    used = 0
    for item in candidates:
        remaining = max_chars - used
        if remaining <= 0 or len(selected) >= max_files:
            break
        content = item.content[:remaining]
        if not content:
            continue
        selected.append(
            ContextItem(
                path=item.path,
                content=content,
                score=item.score,
                source_priority=item.source_priority,
            )
        )
        used += len(content)
    logger.info(
        "Project context scan completed",
        extra={"scanned": scanned, "candidates": len(candidates), "selected": len(selected)},
    )
    return selected


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def _walk_steps(steps: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        yield from _walk_steps(step.get("tasks", []))


def _ignored_path(path: Path, project_root: Path) -> bool:
    relative = path.relative_to(project_root)
    ignored_parts = {".git", ".agent-state", "__pycache__", ".pytest_cache", "node_modules"}
    return any(part in ignored_parts for part in relative.parts)


def _source_priority(relative_path: str) -> int:
    parts = Path(relative_path).parts
    if not parts:
        return 0
    if "memory" in parts:
        return 3
    if parts[0] == "agent-config":
        return 1
    if parts[0] == "docs" or "architecture" in Path(relative_path).name.casefold():
        return 2
    return 0
