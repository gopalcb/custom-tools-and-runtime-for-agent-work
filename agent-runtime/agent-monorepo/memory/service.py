"""Feature-gated memory retrieval and deterministic extraction placeholder."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from .retrieval import MemoryHit, MemoryRetriever

if TYPE_CHECKING:
    from ..events import RuntimeEvent


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    retrieval_enabled: bool = False
    extraction_enabled: bool = False


class MemoryService:
    """Own memory policy while extraction remains intentionally unimplemented.

    Future ingestion should validate approved candidates, write durable records,
    and update any derived search index. Completion itself must never trigger an
    LLM call or silently ingest content.
    """

    def __init__(
        self,
        memory_root: str | Path,
        policy: MemoryPolicy | None = None,
        *,
        retrieval_enabled: bool | None = None,
        extraction_enabled: bool | None = None,
    ) -> None:
        base = policy or MemoryPolicy()
        self.policy = MemoryPolicy(
            retrieval_enabled=(
                base.retrieval_enabled
                if retrieval_enabled is None
                else retrieval_enabled
            ),
            extraction_enabled=(
                base.extraction_enabled
                if extraction_enabled is None
                else extraction_enabled
            ),
        )
        self.retriever = MemoryRetriever(memory_root)

    def retrieve(
        self,
        query: str,
        records: Iterable[Mapping[str, Any]],
        *,
        allowed_paths: Sequence[str | Path] | None = None,
        metadata_filter: Mapping[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryHit]:
        if not self.policy.retrieval_enabled:
            return []
        return self.retriever.retrieve(
            query,
            records,
            allowed_paths=allowed_paths,
            metadata_filter=metadata_filter,
            limit=limit,
        )

    def should_extract(self, _events: Iterable["RuntimeEvent"] | None = None) -> bool:
        return self.policy.extraction_enabled

    def prepare_candidates(
        self,
        _events: Iterable["RuntimeEvent"],
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        # Extraction deliberately stays deterministic until an explicit extractor
        # and review/ingestion policy are implemented.
        result: dict[str, Any] = {
            "status": "enabled" if self.policy.extraction_enabled else "disabled",
            "candidates": [],
        }
        if output_path is not None:
            _write_json(Path(output_path), result)
        return result


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
