"""
Smoke tests for Playwright browser session helpers.

The tests avoid launching Chromium so they can run without browser binaries.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from chrome_browser import check_page_open, read_session, write_session


def test_session_file_and_closed_browser_check() -> None:
    """Verify session metadata helpers and inactive browser reporting."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "session.json"
        write_session(path, {"session_id": "test-session", "url": "about:blank"})
        assert read_session(path)["session_id"] == "test-session"
        result = check_page_open("http://example.invalid", path)
        assert result["open"] is False
        assert result["session"]["url"] == "about:blank"


def main() -> int:
    """Run Playwright helper smoke tests."""
    test_session_file_and_closed_browser_check()
    print("playwright-ui-testing tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
