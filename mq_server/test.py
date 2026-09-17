"""
Smoke tests for compact MQ handler behavior.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from handler import process_event


def test_process_memory_and_workflow_events() -> None:
    """Verify the handler dispatches memory and workflow topics."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        memory = process_event(
            root,
            {
                "event_id": "evt-memory",
                "topic": "memory-store",
                "sender": "test",
                "payload": {
                    "original_task": "MQ memory smoke",
                    "summary": "Stored through MQ.",
                    "validation": "process_event passed.",
                },
            },
        )
        workflow = process_event(root, {"event_id": "evt-workflow", "topic": "run-workflow", "payload": {"workflow": "analysis"}})
        assert memory["stored"] == 1
        assert workflow["workflow"] == "analysis"


def main() -> int:
    """Run MQ smoke tests."""
    test_process_memory_and_workflow_events()
    print("mq_server tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
