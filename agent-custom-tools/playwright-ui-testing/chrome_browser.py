"""
Owns persistent Chromium startup for the compact Playwright UI testing tool.

The module keeps one in-process Playwright context and writes a small session
file so follow-up tool calls can see which page/profile the browser last used.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SESSION_FILE = Path(".agent-state/playwright-ui-testing/session.json")
BROWSER_STATE: dict[str, Any] = {"playwright": None, "context": None, "page": None}


def utc_now() -> str:
    """Return the current UTC timestamp for session metadata."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def playwright_runtime() -> Any:
    """Import Playwright lazily and raise an actionable error when missing."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        raise RuntimeError("Install Playwright with `pip install playwright` and run `playwright install chromium`.") from error
    return sync_playwright


def session_path(path: str | Path | None = None) -> Path:
    """Return the session metadata path."""
    return Path(path or SESSION_FILE)


def write_session(path: Path, metadata: dict) -> None:
    """Persist the latest browser/page metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_session(path: str | Path | None = None) -> dict:
    """Read the previous browser session metadata when it exists."""
    target = session_path(path)
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def open_chrome(
    headless: bool = False,
    user_data_dir: str | Path | None = None,
    session_file: str | Path | None = None,
) -> dict:
    """Open or reuse a persistent Chromium context and record its session id."""
    context = BROWSER_STATE.get("context")
    if context is not None:
        page = get_page()
        return {
            "ok": True,
            "reused": True,
            "session_id": read_session(session_file).get("session_id"),
            "url": page.url,
        }

    sync_playwright = playwright_runtime()
    playwright = sync_playwright().start()
    profile_dir = Path(user_data_dir or ".agent-state/playwright-ui-testing/chrome-profile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        viewport={"width": 1440, "height": 1000},
        args=["--disable-background-networking"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    session_id = f"chrome-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    BROWSER_STATE.update({"playwright": playwright, "context": context, "page": page})
    write_session(
        session_path(session_file),
        {
            "session_id": session_id,
            "created_at": utc_now(),
            "user_data_dir": str(profile_dir),
            "url": page.url,
        },
    )
    return {"ok": True, "reused": False, "session_id": session_id, "url": page.url}


def get_page(
    url: str | None = None,
    headless: bool = False,
    session_file: str | Path | None = None,
) -> Any:
    """Return the active page, opening Chrome and navigating when needed."""
    if BROWSER_STATE.get("context") is None:
        open_chrome(headless=headless, session_file=session_file)
    context = BROWSER_STATE["context"]
    page = BROWSER_STATE.get("page")
    if page is None or page.is_closed():
        page = context.pages[0] if context.pages else context.new_page()
        BROWSER_STATE["page"] = page
    if url and page.url != url:
        page.goto(url, wait_until="domcontentloaded")
    metadata = read_session(session_file)
    metadata.update({"url": page.url, "updated_at": utc_now()})
    write_session(session_path(session_file), metadata)
    return page


def check_page_open(url: str | None = None, session_file: str | Path | None = None) -> dict:
    """Report whether the requested page is open in the active browser context."""
    context = BROWSER_STATE.get("context")
    metadata = read_session(session_file)
    if context is None:
        return {"open": False, "reason": "no active in-process browser", "session": metadata}
    pages = [page for page in context.pages if not page.is_closed()]
    urls = [page.url for page in pages]
    if url:
        matched = next((page_url for page_url in urls if page_url == url), None)
        return {"open": matched is not None, "url": matched, "urls": urls, "session": metadata}
    return {"open": bool(pages), "url": urls[0] if urls else None, "urls": urls, "session": metadata}
