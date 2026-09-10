"""Run structured, source-aware web research through the shared Codex client.

This module owns the search prompt, Codex call, JSON validation, and Markdown
rendering. ``cli.py`` only constructs requests and presents saved results.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from agent_monorepo.codex_client import CodexSDKClient

from model import DEFAULT_SEARCH_INSTRUCTIONS, SearchRequest
from validation import validate_search_request, validate_search_response


def build_search_prompt(request: SearchRequest) -> str:
    """Build the bounded research prompt sent to Codex."""
    return (
        "Research the following request using current external sources. "
        "Return a concise answer and cite every source used.\n\n"
        f"Research request:\n{request.query}"
    )


def search_response_schema() -> dict[str, Any]:
    """Return the JSON schema Codex must use for web-search results."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["title", "url", "summary"],
                },
            },
        },
        "required": ["answer", "sources"],
    }


def search(request: SearchRequest) -> dict[str, Any]:
    """Run a search and return a JSON-compatible response for agents."""
    validated_request = validate_search_request(request)
    with CodexSDKClient(validated_request.cwd, model=validated_request.model) as client:
        payload = client.run_structured(
            build_search_prompt(validated_request),
            search_response_schema(),
            sandbox="read_only",
            model=validated_request.model,
            developer_instructions=validated_request.instructions,
            ephemeral=True,
        )
    return validate_search_response(payload, validated_request.query).to_dict()


def json_to_markdown(response: dict) -> str:
    """Convert a JSON-compatible search response into readable Markdown."""
    query = response.get("query") if isinstance(response, dict) else None
    if not isinstance(query, str) or not query.strip():
        raise ValueError("search response query must be a non-empty string")
    validated_response = validate_search_response(response, query.strip())
    source_lines = [
        f"- [{source.title}]({source.url}): {source.summary}"
        for source in validated_response.sources
    ]
    sources = "\n".join(source_lines) if source_lines else "No sources were returned."
    return (
        "# Web Search Result\n\n"
        f"## Query\n\n{validated_response.query}\n\n"
        f"## Answer\n\n{validated_response.answer}\n\n"
        f"## Sources\n\n{sources}\n"
    )


def save_markdown(response: dict, output_directory: str | Path = "output") -> Path:
    """Convert a JSON response to Markdown and save it with a unique timestamp."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone()
    stem = f"web-search-{timestamp:%Y%m%d_%H%M%S}"
    path = output / f"{stem}.md"
    suffix = 1
    while path.exists():
        path = output / f"{stem}-{suffix}.md"
        suffix += 1
    path.write_text(json_to_markdown(response), encoding="utf-8")
    return path


__all__ = [
    "DEFAULT_SEARCH_INSTRUCTIONS",
    "build_search_prompt",
    "json_to_markdown",
    "save_markdown",
    "search",
    "search_response_schema",
]
