"""Validation for web-search request and structured response payloads."""

from __future__ import annotations

from pathlib import Path

from model import SearchRequest, SearchResponse, SearchSource


def validate_search_request(request: SearchRequest) -> SearchRequest:
    """Validate and normalize one web-search request."""
    if not isinstance(request, SearchRequest):
        raise TypeError("request must be a SearchRequest")
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
    """Validate Codex's structured response and return its domain model."""
    if not isinstance(payload, dict):
        raise TypeError("search response must be a JSON object")
    answer = payload.get("answer")
    sources = payload.get("sources")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("search response answer must be a non-empty string")
    if not isinstance(sources, list):
        raise ValueError("search response sources must be a list")

    validated_sources: list[SearchSource] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each search source must be a JSON object")
        title = source.get("title")
        url = source.get("url")
        summary = source.get("summary")
        if not all(isinstance(value, str) and value.strip() for value in (title, url, summary)):
            raise ValueError("each search source needs non-empty title, url, and summary")
        validated_sources.append(
            SearchSource(title=title.strip(), url=url.strip(), summary=summary.strip())
        )
    return SearchResponse(query=query, answer=answer.strip(), sources=tuple(validated_sources))
