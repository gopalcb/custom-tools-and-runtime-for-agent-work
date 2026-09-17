"""
Smoke tests for compact knowledge-search helpers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from log_search import detect_log_errors, search_logs
from web_search import json_to_markdown, validate_search_response


def test_web_response_and_log_search() -> None:
    """Verify structured response validation and local log scanning."""
    response = {
        "query": "Question",
        "answer": "Answer",
        "sources": [{"title": "Source", "url": "https://example.com", "summary": "Evidence"}],
    }
    assert validate_search_response(response, "Question").answer == "Answer"
    assert "[Source](https://example.com)" in json_to_markdown(response)

    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "system.log"
        log.write_text("INFO ok\nERROR failure\n", encoding="utf-8")
        matches = search_logs(directory, "failure")
        errors = detect_log_errors(directory, ".")
        assert len(matches["matches"]) == 1
        assert len(errors["errors"]) == 1


def main() -> int:
    """Run knowledge-search smoke tests."""
    test_web_response_and_log_search()
    print("knowledge-search tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
