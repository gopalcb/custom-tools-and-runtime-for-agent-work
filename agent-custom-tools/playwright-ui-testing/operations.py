"""
Provides page inspection operations for Playwright UI testing.

Browser lifecycle belongs to chrome_browser.py; this file captures screenshots,
network activity, console failures, and basic hydration state from an open page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chrome_browser import get_page


def capture_page_screenshot(
    url: str | None = None,
    output: str | Path = ".agent-state/playwright-ui-testing/screenshot.png",
    full_page: bool = True,
) -> dict:
    """Capture a PNG screenshot for the active or requested page."""
    page = get_page(url)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(target), full_page=full_page)
    return {"ok": True, "path": str(target), "url": page.url}


def trace_network_calls(
    url: str | None = None,
    duration_ms: int = 1500,
    reload: bool = False,
) -> dict:
    """Collect request, response, and failure records for a short browser window."""
    page = get_page(url)
    calls: list[dict[str, Any]] = []

    def record_request(request: Any) -> None:
        """Record one outgoing request."""
        calls.append({"event": "request", "method": request.method, "url": request.url, "resource_type": request.resource_type})

    def record_response(response: Any) -> None:
        """Record one response status."""
        calls.append({"event": "response", "status": response.status, "url": response.url})

    def record_failure(request: Any) -> None:
        """Record one network failure."""
        calls.append({"event": "failed", "url": request.url, "failure": request.failure})

    page.on("request", record_request)
    page.on("response", record_response)
    page.on("requestfailed", record_failure)
    if reload:
        page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(max(0, int(duration_ms)))
    return {"ok": True, "url": page.url, "count": len(calls), "calls": calls}


def get_console_errors(url: str | None = None, duration_ms: int = 1000, reload: bool = False) -> dict:
    """Collect browser console messages at error level."""
    page = get_page(url)
    errors: list[dict[str, str]] = []

    def record_console(message: Any) -> None:
        """Record one console error message."""
        if message.type == "error":
            errors.append({"type": message.type, "text": message.text, "location": str(message.location)})

    page.on("console", record_console)
    if reload:
        page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(max(0, int(duration_ms)))
    return {"ok": not errors, "url": page.url, "count": len(errors), "errors": errors}


def validate_dom_hydration(url: str | None = None) -> dict:
    """Check common browser and framework signals for a hydrated DOM."""
    page = get_page(url)
    result = page.evaluate(
        """
        () => {
          const root = document.querySelector('#root, #app, [data-reactroot], [data-nextjs-scroll-focus-boundary]');
          const bodyText = (document.body && document.body.innerText || '').trim();
          const scripts = Array.from(document.scripts).filter((script) => script.src).length;
          const frameworkMarkers = {
            next: Boolean(window.__NEXT_DATA__),
            reactDevtools: Boolean(window.__REACT_DEVTOOLS_GLOBAL_HOOK__),
            vite: Boolean(Array.from(document.scripts).find((script) => script.src.includes('/@vite/'))),
          };
          return {
            readyState: document.readyState,
            hasBodyText: bodyText.length > 0,
            bodyTextLength: bodyText.length,
            hasRoot: Boolean(root),
            scriptCount: scripts,
            frameworkMarkers,
          };
        }
        """
    )
    hydrated = result["readyState"] == "complete" and result["hasBodyText"] and result["scriptCount"] > 0
    return {"ok": bool(hydrated), "url": page.url, "hydrated": bool(hydrated), "signals": result}
