"""
Smoke tests for the compact custom-agent runtime root.

The test exercises the runtime facade without starting servers or browser
sessions, keeping validation deterministic and local.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from runtime import CompactAgentRuntime


def test_runtime_resolves_workflow_and_memory() -> None:
    """Verify workflow resolution plus memory store/search through the facade."""
    with tempfile.TemporaryDirectory() as directory:
        runtime = CompactAgentRuntime(Path(directory))
        resolved = runtime.resolve_workflow("analysis")
        assert resolved["workflow"] == "analysis"
        assert resolved["steps"][0]["id"] == "pre-work-health"

        stored = runtime.remember(
            "Root custom-agent-tools-and-runtime test",
            "Stored a memory record through the facade.",
            "test_runtime_resolves_workflow_and_memory passed.",
            ["my-system-libs/runtime.py"],
        )
        found = runtime.search_memory("custom agent runtime memory")
        assert stored["stored"] == 1
        assert found["count"] == 1


def main() -> int:
    """Run root smoke tests."""
    test_runtime_resolves_workflow_and_memory()
    print("my-system-libs root tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
