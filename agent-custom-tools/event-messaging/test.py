"""
Smoke tests for compact file-backed event messaging.
"""

from __future__ import annotations

import tempfile

from bus import MessageBus
from hub import build_default_hub
from models import AgentMessage


def test_send_process_and_error_record() -> None:
    """Verify message lifecycle, hub replies, and error tracking."""
    with tempfile.TemporaryDirectory() as directory:
        bus = MessageBus(directory)
        path = bus.send(AgentMessage("tester", "agent-health", "health.request", {"ping": True}))
        assert bus.pending("agent-health") == [path]
        assert bus.summary()["by_status"] == {"pending": 1}

        processed = build_default_hub(directory).run_once(["agent-health"])
        assert processed == 1
        assert bus.summary()["by_status"]["processed"] == 1
        assert bus.list_records(message_type="health.request.result")

        error = bus.record_error({"message": "boom"})
        assert error["status"] == "active"
        assert bus.resolve_current_error()["status"] == "fixed"


def main() -> int:
    """Run event messaging smoke tests."""
    test_send_process_and_error_record()
    print("event-messaging tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
