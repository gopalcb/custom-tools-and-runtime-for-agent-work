from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class ProjectResolutionError(RuntimeError):
    """Raised when no project can be resolved safely."""


@dataclass(frozen=True)
class ProjectResolution:
    project: str
    path: str
    reason: str


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]*", re.IGNORECASE)


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(value)}


def resolve_project(prompt: str, registry: dict[str, Any], active_project: str | None = None) -> ProjectResolution:
    """Resolve one project without an LLM.

    V1 resolution order:
    1. exact project name in prompt
    2. configured alias phrase in prompt
    3. active project (for follow-up turns)
    4. simple lexical overlap with project descriptions

    Local semantic search intentionally replaces step 4 later.
    """
    prompt_normalized = " ".join(prompt.lower().split())
    projects: dict[str, Any] = {
        name: config
        for name, config in registry.get("projects", {}).items()
        if not config.get("disabled", False)
    }
    if not projects:
        raise ProjectResolutionError("No enabled projects are registered.")

    for project_name, config in projects.items():
        if project_name.lower() in prompt_normalized:
            return ProjectResolution(project_name, config["path"], "explicit project name")

    for project_name, config in projects.items():
        for alias in config.get("aliases", []):
            if alias.lower() in prompt_normalized:
                return ProjectResolution(project_name, config["path"], f"alias: {alias}")

    if active_project and active_project in projects:
        config = projects[active_project]
        return ProjectResolution(active_project, config["path"], "active project continuation")

    prompt_tokens = _tokens(prompt)
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for project_name, config in projects.items():
        candidate = " ".join([project_name, config.get("description", ""), *config.get("aliases", [])])
        score = len(prompt_tokens & _tokens(candidate))
        matches.append((score, project_name, config))

    matches.sort(reverse=True, key=lambda item: item[0])
    best_score, best_name, best_config = matches[0]
    if best_score <= 0:
        raise ProjectResolutionError(
            "Unable to resolve a project deterministically. Specify a project name; "
            "semantic resolution will be added in semantic_search.py later."
        )

    return ProjectResolution(best_name, best_config["path"], f"lexical overlap: {best_score}")
