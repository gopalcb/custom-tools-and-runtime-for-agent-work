"""Run Selenium UI inspections and persist transparent debug artifacts.

This module owns browser automation for `agent-ui-debugger`. Message handling
belongs to `agents_internal_messaging.hub`; this file accepts a validated debug
request, opens Chrome, captures console and network failures, writes artifacts,
and returns a compact result for reply messages.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from agents_internal_messaging.bus import default_message_root

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.chrome.options import Options as ChromeOptions
except ModuleNotFoundError:
    webdriver = None
    ChromeOptions = None
    WebDriverException = Exception


logger = logging.getLogger(__name__)
SAFE_FRAGMENT = re.compile(r"[^A-Za-z0-9_.-]+")
NETWORK_TYPES = frozenset({"XHR", "Fetch"})
MAX_INLINE_ERRORS = 20
MAX_FULL_PAGE_HEIGHT = 20000


@dataclass(frozen=True, slots=True)
class DebugRequest:
    request_id: str
    url: str
    requester: str | None = None
    artifact_root: str | None = None
    wait_seconds: float = 1.0
    viewport_width: int = 1440
    viewport_height: int = 1000
    full_page_screenshot: bool = True
    notes: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DebugRequest":
        """Validate and normalize a message payload into a debug request."""
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("ui_debug_request payload requires a url")
        request_id = str(payload.get("request_id") or f"ui-debug-{uuid4().hex[:12]}")
        requester = payload.get("requester")
        notes = payload.get("notes")
        artifact_root = payload.get("artifact_root")
        return cls(
            request_id=safe_fragment(request_id),
            url=url,
            requester=str(requester) if requester else None,
            artifact_root=str(artifact_root) if artifact_root else None,
            wait_seconds=numeric(payload.get("wait_seconds"), 1.0, 0.0, 30.0),
            viewport_width=int(numeric(payload.get("viewport_width"), 1440, 320, 3840)),
            viewport_height=int(numeric(payload.get("viewport_height"), 1000, 320, 3000)),
            full_page_screenshot=boolean(payload.get("full_page_screenshot"), True),
            notes=str(notes) if notes else None,
        )


@dataclass(frozen=True, slots=True)
class DebugResult:
    ok: bool
    request_id: str
    artifact_dir: Path
    manifest_path: Path
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert a debugger result to a JSON-serializable dictionary."""
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "artifact_dir": str(self.artifact_dir),
            "manifest_path": str(self.manifest_path),
            "summary": self.summary,
        }


def run_debug_request(request: DebugRequest) -> DebugResult:
    """Execute one browser debug request and write a manifest."""
    artifact_dir = build_artifact_dir(request)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    driver: Any | None = None
    errors: list[str] = []
    console = {"logs": [], "errors": []}
    network_errors: list[dict[str, Any]] = []
    screenshot_path: Path | None = None
    page_title = ""

    if webdriver is None or ChromeOptions is None:
        errors.append("Selenium is not installed. Install agent-tools/ui-debugger/requirements.txt.")
    else:
        try:
            driver = open_driver(request)
            driver.execute_cdp_cmd("Network.enable", {})
            driver.get(request.url)
            wait_for_page(driver, request)
            page_title = str(getattr(driver, "title", "") or "")
            console = collect_browser_logs(driver)
            network_errors = collect_network_errors(driver.get_log("performance"))
            screenshot_path = capture_screenshot(driver, artifact_dir, request)
        except Exception as exc:
            logger.exception("UI debug request failed", extra={"request_id": request.request_id})
            errors.append(error_text(exc))
        finally:
            close_driver(driver)

    summary = {
        "url": request.url,
        "request_id": request.request_id,
        "page_title": page_title,
        "ok": not errors and not console["errors"] and not network_errors,
        "console_log_count": len(console["logs"]),
        "console_error_count": len(console["errors"]),
        "network_issue_count": len(network_errors),
        "console_errors": console["errors"][:MAX_INLINE_ERRORS],
        "network_errors": network_errors[:MAX_INLINE_ERRORS],
        "errors": errors,
        "screenshot_path": str(screenshot_path) if screenshot_path else None,
    }
    paths = write_result_files(artifact_dir, request, summary, console, network_errors)
    summary["artifact_paths"] = {key: str(path) for key, path in paths.items()}
    result = DebugResult(
        ok=bool(summary["ok"]),
        request_id=request.request_id,
        artifact_dir=artifact_dir,
        manifest_path=paths["manifest"],
        summary=summary,
    )
    logger.info("UI debug request completed", extra={"request_id": request.request_id, "ok": result.ok})
    return result


def build_artifact_dir(request: DebugRequest) -> Path:
    """Resolve the artifact directory for a request."""
    root = Path(request.artifact_root).expanduser() if request.artifact_root else default_message_root() / "debug-sessions"
    return root / safe_fragment(request.request_id)


def open_driver(request: DebugRequest) -> Any:
    """Create a Chrome WebDriver configured for browser and performance logs."""
    if webdriver is None or ChromeOptions is None:
        raise RuntimeError("Selenium is not installed.")
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={request.viewport_width},{request.viewport_height}")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    return webdriver.Chrome(options=options)


def wait_for_page(driver: Any, request: DebugRequest) -> None:
    """Wait for document readiness and the configured settling time."""
    deadline = time.time() + 20
    while time.time() < deadline:
        state = driver.execute_script("return document.readyState")
        if state == "complete":
            break
        time.sleep(0.1)
    if request.wait_seconds:
        time.sleep(request.wait_seconds)


def collect_browser_logs(driver: Any) -> dict[str, list[dict[str, Any]]]:
    """Read browser console logs and split error-level entries."""
    try:
        logs = list(driver.get_log("browser"))
    except WebDriverException:
        logs = []
    normalized: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in logs:
        entry = {
            "level": str(item.get("level") or ""),
            "message": str(item.get("message") or ""),
            "timestamp": item.get("timestamp"),
            "source": item.get("source"),
        }
        normalized.append(entry)
        if entry["level"].upper() in {"SEVERE", "ERROR"}:
            errors.append(entry)
    return {"logs": normalized, "errors": errors}


def collect_network_errors(entries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Parse Chrome performance logs and return actual failed fetch/XHR requests."""
    requests: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    for entry in entries:
        try:
            envelope = json.loads(str(entry.get("message") or "{}"))
        except json.JSONDecodeError:
            continue
        message = envelope.get("message") if isinstance(envelope, dict) else None
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        params = message.get("params")
        if not isinstance(params, dict):
            continue
        request_id = str(params.get("requestId") or "")
        if method == "Network.requestWillBeSent":
            request = params.get("request") if isinstance(params.get("request"), dict) else {}
            requests[request_id] = {
                "url": request.get("url"),
                "method": request.get("method"),
                "resource_type": params.get("type"),
            }
        elif method == "Network.responseReceived":
            response = params.get("response") if isinstance(params.get("response"), dict) else {}
            status = int(response.get("status") or 0)
            resource_type = str(params.get("type") or requests.get(request_id, {}).get("resource_type") or "")
            if status >= 400 and (resource_type in NETWORK_TYPES or resource_type == "Document"):
                request = requests.get(request_id, {})
                failures.append(
                    {
                        "type": "http",
                        "resource_type": resource_type,
                        "status": status,
                        "method": request.get("method"),
                        "url": response.get("url") or request.get("url"),
                    }
                )
        elif method == "Network.loadingFailed":
            canceled = bool(params.get("canceled"))
            resource_type = str(params.get("type") or requests.get(request_id, {}).get("resource_type") or "")
            if not canceled and (resource_type in NETWORK_TYPES or resource_type == "Document"):
                request = requests.get(request_id, {})
                failures.append(
                    {
                        "type": "network",
                        "resource_type": resource_type,
                        "method": request.get("method"),
                        "url": request.get("url"),
                        "error_text": params.get("errorText"),
                    }
                )
    return failures


def capture_screenshot(driver: Any, artifact_dir: Path, request: DebugRequest) -> Path:
    """Save a viewport or full-page PNG screenshot."""
    screenshot_path = artifact_dir / "screenshot.png"
    if request.full_page_screenshot:
        try:
            metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
            content = metrics.get("contentSize") if isinstance(metrics, dict) else {}
            width = int(max(request.viewport_width, math.ceil(float(content.get("width", request.viewport_width)))))
            height = int(max(request.viewport_height, math.ceil(float(content.get("height", request.viewport_height)))))
            driver.set_window_size(width, min(height, MAX_FULL_PAGE_HEIGHT))
        except Exception:
            driver.set_window_size(request.viewport_width, request.viewport_height)
    driver.save_screenshot(str(screenshot_path))
    return screenshot_path


def close_driver(driver: Any | None) -> None:
    """Close a WebDriver session while preserving the main result."""
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        logger.warning("Unable to close Selenium driver cleanly")


def write_result_files(
    artifact_dir: Path,
    request: DebugRequest,
    summary: Mapping[str, Any],
    console: Mapping[str, Any],
    network_errors: list[dict[str, Any]],
) -> dict[str, Path]:
    """Persist console logs, network errors, and the manifest JSON."""
    console_path = artifact_dir / "console.json"
    network_path = artifact_dir / "network-errors.json"
    manifest_path = artifact_dir / "manifest.json"
    console_path.write_text(json.dumps(console, indent=2, sort_keys=True), encoding="utf-8")
    network_path.write_text(json.dumps(network_errors, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "generated_at": utc_now_iso(),
        "request": {
            "request_id": request.request_id,
            "url": request.url,
            "requester": request.requester,
            "notes": request.notes,
            "wait_seconds": request.wait_seconds,
            "viewport_width": request.viewport_width,
            "viewport_height": request.viewport_height,
            "full_page_screenshot": request.full_page_screenshot,
        },
        "summary": dict(summary),
        "artifacts": {
            "console": str(console_path),
            "network_errors": str(network_path),
            "screenshot": summary.get("screenshot_path"),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"manifest": manifest_path, "console": console_path, "network_errors": network_path}


def safe_fragment(value: str) -> str:
    """Convert user-provided ids into safe path fragments."""
    fragment = SAFE_FRAGMENT.sub("-", value.strip()).strip("-._")
    return fragment[:96] or f"ui-debug-{uuid4().hex[:12]}"


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 form."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def error_text(error: Any) -> str:
    """Render an exception or unknown value as text."""
    if isinstance(error, BaseException):
        return f"{type(error).__name__}: {error}"
    return str(error)


def numeric(value: Any, default: float, minimum: float, maximum: float) -> float:
    """Normalize numeric payload values with bounds."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def boolean(value: Any, default: bool) -> bool:
    """Normalize boolean-like payload values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default
