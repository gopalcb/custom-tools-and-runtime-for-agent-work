"""
Smoke tests for compact strategy feedback.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

from feedback_coordinator import StrategyFeedbackCoordinator, fallback_analysis, parse_analysis


def test_parse_and_fallback_analysis() -> None:
    """Verify JSON parsing and requested-change fallback behavior."""
    parsed = parse_analysis('```json\n{"feedback_type":"preference","rework":{"needed":false},"memory_actions":[]}\n```')
    assert parsed["feedback_type"] == "preference"
    analysis = fallback_analysis({"feedback": "Good", "requested_change": "Make it smaller", "store_work_memory": False})
    assert analysis["feedback_type"] == "rework_request"
    assert analysis["memory_actions"] == []


def test_fixture_collection() -> None:
    """Verify feedback collection can use a fixture without GUI startup."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = root / "feedback.json"
        fixture.write_text(json.dumps({"status": "submitted", "feedback": "Remember this", "store_work_memory": True}), encoding="utf-8")
        old = os.environ.get("AGENT_STRATEGY_FEEDBACK_RESPONSE")
        os.environ["AGENT_STRATEGY_FEEDBACK_RESPONSE"] = str(fixture)
        try:
            result = asyncio.run(
                StrategyFeedbackCoordinator(root).collect_feedback(
                    {"run_id": "run-1", "session_id": "session-1", "prompt": "Prompt"}
                )
            )
        finally:
            if old is None:
                os.environ.pop("AGENT_STRATEGY_FEEDBACK_RESPONSE", None)
            else:
                os.environ["AGENT_STRATEGY_FEEDBACK_RESPONSE"] = old
        assert result["status"] == "submitted"
        assert Path(result["artifact_path"]).is_file()


def main() -> int:
    """Run strategy feedback smoke tests."""
    test_parse_and_fallback_analysis()
    test_fixture_collection()
    print("strategy-feedback tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
