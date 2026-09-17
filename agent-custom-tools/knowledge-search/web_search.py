"""
Runs structured Codex-backed web search for the compact tool library.

The implementation mirrors the active flat monorepo search tool but keeps the
Codex SDK import lazy so local validation can run without a live SDK session.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_SEARCH_INSTRUCTIONS = (
    "You are a careful web-research assistant. Research the user's question "
    "using current external sources. Prefer primary sources, distinguish facts "
    "from inference, include source URLs, and say when evidence is unavailable."
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

    def to_dict(self) -> dict:
        """Return this source as JSON-compatible data."""
        return {"title": self.title, "url": self.url, "summary": self.summary}


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Structured answer and source list returned from web search."""

    query: str
    answer: str
    sources: tuple[SearchSource, ...]

    def to_dict(self) -> dict:
        """Return this response as JSON-compatible data."""
        return {"query": self.query, "answer": self.answer, "sources": [source.to_dict() for source in self.sources]}


def codex_client_class(cwd: str | Path) -> Any:
    """Load the shared Codex SDK client from a normal or compact checkout."""
    try:
        from agent_monorepo.codex_client import CodexSDKClient
    except ModuleNotFoundError:
        root = Path(cwd).resolve()
        candidate = root / "agent-runtime" / "agent-monorepo"
        if candidate.exists() and str(candidate.parent) not in sys.path:
            sys.path.insert(0, str(candidate.parent))
        from agent_monorepo.codex_client import CodexSDKClient
    return CodexSDKClient


def validate_search_request(request: SearchRequest) -> SearchRequest:
    """Validate and normalize one web-search request."""
    if not isinstance(request.query, str) or not request.query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(request.instructions, str) or not request.instructions.strip():
        raise ValueError("instructions must be a non-empty string")
    if not isinstance(request.cwd, (str, Path)):
        raise TypeError("cwd must be a string or Path")
    if not isinstance(request.model, (str, type(None))):
        raise TypeError("model must be a string or None")
    return SearchRequest(
        query=request.query.strip(),
        instructions=request.instructions.strip(),
        cwd=request.cwd,
        model=request.model.strip() if isinstance(request.model, str) else None,
    )


def validate_search_response(payload: dict, query: str) -> SearchResponse:
    """Validate a structured search response."""
    if not isinstance(payload, dict):
        raise TypeError("search response must be a JSON object")
    answer = payload.get("answer")
    sources = payload.get("sources")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("search response answer must be a non-empty string")
    if not isinstance(sources, list):
        raise ValueError("search response sources must be a list")
    validated = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each search source must be a JSON object")
        title = source.get("title")
        url = source.get("url")
        summary = source.get("summary")
        if not all(isinstance(value, str) and value.strip() for value in (title, url, summary)):
            raise ValueError("each search source needs non-empty title, url, and summary")
        validated.append(SearchSource(title.strip(), url.strip(), summary.strip()))
    return SearchResponse(query=query, answer=answer.strip(), sources=tuple(validated))


def build_search_prompt(request: SearchRequest) -> str:
    """Build the bounded research prompt sent to Codex."""
    return (
        "Research the following request using current external sources. "
        "Return a concise answer and cite every source used.\n\n"
        f"Research request:\n{request.query}"
    )


def search_response_schema() -> dict:
    """Return the JSON schema expected from Codex."""
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


def search(request: SearchRequest) -> dict:
    """Run a source-aware web search and return agent-friendly JSON."""
    validated = validate_search_request(request)
    client_class = codex_client_class(validated.cwd)
    with client_class(validated.cwd, model=validated.model) as client:
        payload = client.run_structured(
            build_search_prompt(validated),
            search_response_schema(),
            sandbox="read_only",
            model=validated.model,
            developer_instructions=validated.instructions,
            ephemeral=True,
        )
    return validate_search_response(payload, validated.query).to_dict()


def run_web_search(payload: dict) -> dict:
    """Run web search from an MQ/tool payload."""
    return search(
        SearchRequest(
            query=str(payload.get("query") or payload.get("prompt") or ""),
            instructions=str(payload.get("instructions") or DEFAULT_SEARCH_INSTRUCTIONS),
            cwd=payload.get("cwd") or ".",
            model=payload.get("model"),
        )
    )


def json_to_markdown(response: dict) -> str:
    """Convert a structured search response to Markdown."""
    query = response.get("query") if isinstance(response, dict) else None
    if not isinstance(query, str) or not query.strip():
        raise ValueError("search response query must be a non-empty string")
    validated = validate_search_response(response, query.strip())
    source_lines = [f"- [{source.title}]({source.url}): {source.summary}" for source in validated.sources]
    sources = "\n".join(source_lines) if source_lines else "No sources were returned."
    return f"# Web Search Result\n\n## Query\n\n{validated.query}\n\n## Answer\n\n{validated.answer}\n\n## Sources\n\n{sources}\n"


def save_markdown(response: dict, output_directory: str | Path = "output") -> Path:
    """Save a structured search response as Markdown."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone()
    path = output / f"web-search-{timestamp:%Y%m%d_%H%M%S}.md"
    suffix = 1
    while path.exists():
        path = output / f"web-search-{timestamp:%Y%m%d_%H%M%S}-{suffix}.md"
        suffix += 1
    path.write_text(json_to_markdown(response), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run web search from the command line."""
    parser = argparse.ArgumentParser(description="Run compact Codex-backed web search")
    parser.add_argument("--payload")
    parser.add_argument("--query", "--prompt", dest="query")
    parser.add_argument("--instructions", default=DEFAULT_SEARCH_INSTRUCTIONS)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--model")
    parser.add_argument("--output-directory", default="output")
    args = parser.parse_args(argv)
    payload = json.loads(args.payload) if args.payload else {"query": args.query, "instructions": args.instructions, "cwd": args.cwd, "model": args.model}
    response = run_web_search(payload)
    markdown_path = save_markdown(response, payload.get("output_directory") or args.output_directory)
    print(json.dumps({"response": response, "markdown_path": str(markdown_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
