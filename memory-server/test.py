"""
Smoke tests for the compact memory server.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from server import health, search_memory, store_memory


def test_store_search_and_health() -> None:
    """Verify health, deterministic storage, and lexical retrieval."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assert health(root)["ready"] is True
        stored = store_memory(
            root,
            {
                "original_task": "Memory smoke",
                "summary": "Stored compact memory.",
                "validation": "Smoke test passed.",
                "files": ["my-system-libs/memory-server/server.py"],
            },
            {"topic": "memory-store", "sender": "test"},
        )
        found = search_memory(root, {"query": "compact memory"})
        assert stored["stored"] == 1
        assert found["count"] == 1


def main() -> int:
    """Run memory-server smoke tests."""
    test_store_search_and_health()
    print("memory-server tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
