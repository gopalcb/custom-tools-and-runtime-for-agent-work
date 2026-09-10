"""Small lexical memory retriever with no external search dependency."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class MemoryHit:
    path: str
    content: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


class MemoryRetriever:
    """Rank text records using lexical, metadata, and recency signals.

    Records are mappings with ``path`` and ``content`` fields and an optional
    ``metadata`` mapping. Paths must resolve beneath ``memory_root`` and, when
    supplied, one of ``allowed_paths``. This interface can later host vector
    and reranking stages without changing callers.
    """

    def __init__(self, memory_root: str | Path) -> None:
        self.memory_root = Path(memory_root).resolve()

    def retrieve(
        self,
        query: str,
        records: Iterable[Mapping[str, Any]],
        *,
        allowed_paths: Sequence[str | Path] | None = None,
        metadata_filter: Mapping[str, Any] | None = None,
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[MemoryHit]:
        if limit <= 0:
            return []
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        roots = self._allowed_roots(allowed_paths)
        current_time = now or datetime.now(timezone.utc)
        results: list[MemoryHit] = []

        for record in records:
            path = self._safe_record_path(record.get("path"), roots)
            if path is None:
                continue
            content = str(record.get("content", ""))
            metadata = dict(record.get("metadata") or {})
            if not _metadata_matches(metadata, metadata_filter):
                continue
            score = _lexical_score(query, query_tokens, content, metadata)
            if score <= 0:
                continue
            score *= _metadata_weight(metadata)
            score *= _recency_weight(metadata, current_time)
            results.append(
                MemoryHit(
                    path=path.relative_to(self.memory_root).as_posix(),
                    content=content,
                    score=round(score, 8),
                    metadata=metadata,
                )
            )

        return sorted(results, key=lambda hit: (-hit.score, hit.path))[:limit]

    def _allowed_roots(
        self, allowed_paths: Sequence[str | Path] | None
    ) -> tuple[Path, ...]:
        if allowed_paths is None:
            return (self.memory_root,)
        roots: list[Path] = []
        for value in allowed_paths:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = self.memory_root / candidate
            candidate = candidate.resolve()
            if _is_within(candidate, self.memory_root):
                roots.append(candidate)
        return tuple(roots)

    def _safe_record_path(self, value: Any, roots: tuple[Path, ...]) -> Path | None:
        if not isinstance(value, (str, Path)) or not roots:
            return None
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.memory_root / candidate
        candidate = candidate.resolve()
        if not _is_within(candidate, self.memory_root):
            return None
        if not any(_is_within(candidate, root) for root in roots):
            return None
        return candidate


def retrieve(
    query: str,
    records: Iterable[Mapping[str, Any]],
    *,
    memory_root: str | Path,
    **options: Any,
) -> list[MemoryHit]:
    """Convenience wrapper for callers that do not retain a retriever."""
    return MemoryRetriever(memory_root).retrieve(query, records, **options)


def _tokens(value: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN.finditer(value)}


def _lexical_score(
    query: str,
    query_tokens: set[str],
    content: str,
    metadata: Mapping[str, Any],
) -> float:
    searchable_metadata = " ".join(
        str(value)
        for key, value in metadata.items()
        if key in {"title", "tags", "agent_id", "project", "kind"}
    )
    content_tokens = _tokens(f"{content} {searchable_metadata}")
    matched = query_tokens & content_tokens
    if not matched:
        return 0.0
    coverage = len(matched) / len(query_tokens)
    specificity = sum(1.0 / math.sqrt(1 + content.lower().count(token)) for token in matched)
    phrase_bonus = 0.25 if query.strip().lower() in content.lower() else 0.0
    return coverage + (specificity / len(query_tokens)) * 0.25 + phrase_bonus


def _metadata_matches(
    metadata: Mapping[str, Any], wanted: Mapping[str, Any] | None
) -> bool:
    if not wanted:
        return True
    for key, expected in wanted.items():
        actual = metadata.get(key)
        if isinstance(actual, (list, tuple, set)):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


def _metadata_weight(metadata: Mapping[str, Any]) -> float:
    raw = metadata.get("weight", 1.0)
    try:
        return min(4.0, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return 1.0


def _recency_weight(metadata: Mapping[str, Any], now: datetime) -> float:
    raw = metadata.get("updated_at") or metadata.get("created_at")
    if not isinstance(raw, str):
        return 1.0
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age_days = max(
            0.0,
            (now.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
            / 86400,
        )
    except ValueError:
        return 1.0
    return 1.0 + 0.25 / (1.0 + age_days / 30.0)


def _is_within(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents
