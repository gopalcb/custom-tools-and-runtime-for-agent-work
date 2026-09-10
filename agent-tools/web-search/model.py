"""Data structures for Codex-backed web-search requests and results.

The service validates these values at its boundary, then returns each result as
a JSON-compatible dictionary through ``SearchResponse.to_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SEARCH_INSTRUCTIONS = (
    "You are a careful web-research assistant. Research the user's question "
    "using current external sources available to Codex. Prefer authoritative "
    "primary sources, distinguish facts from inference, include source URLs, "
    "and say when evidence is unavailable."
)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Input required to perform one source-aware web search."""

    query: str
    instructions: str = DEFAULT_SEARCH_INSTRUCTIONS
    cwd: str | Path = "."
    model: str | None = None


@dataclass(frozen=True, slots=True)
class SearchSource:
    """One source supporting a search result."""

    title: str
    url: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        """Return the source in a JSON-compatible shape."""
        return {"title": self.title, "url": self.url, "summary": self.summary}


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Structured answer and source list returned from a web search."""

    query: str
    answer: str
    sources: tuple[SearchSource, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the response as a JSON-compatible object for agents."""
        return {
            "query": self.query,
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
        }
