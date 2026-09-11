# UI Debugger Architecture

## Purpose

`ui-debugger` is the deterministic browser-inspection tool used by the
`agent-ui-debugger` agent. It opens a supplied UI URL with Selenium, captures a
full-page screenshot, records browser console output, filters Chrome DevTools
network events to actual request failures, and writes artifacts under the
messaging tree so the requester receives small transparent reply messages.

## Project Structure

```text
agent-tools/ui-debugger/
├── ui_debugger/
│   ├── __init__.py
│   ├── cli.py
│   └── runner.py
├── ARCHITECTURE.md
├── code-map.yaml
└── requirements.txt
```

## Main Execution Flow

The messaging hub receives a `ui_debug_request`, builds a `DebugRequest`, and
calls `run_debug_request()`. The runner creates a headless Chrome WebDriver with
browser and performance logging enabled, opens the URL, waits for document load,
captures artifacts, writes `manifest.json`, and returns a compact summary. The
hub sends that summary back to the requester through the message bus.

## Module Responsibilities

- `ui_debugger/runner.py`: owns Selenium setup, browser inspection, network
  filtering, screenshots, artifact persistence, and result shaping.
- `ui_debugger/cli.py`: thin manual entry point for running one debug request
  from a terminal.
- `ui_debugger/__init__.py`: exposes the runner contracts.

## Configuration

Requests may provide `artifact_root`, `wait_seconds`, `viewport_width`,
`viewport_height`, and `full_page_screenshot`. When no artifact root is supplied,
artifacts are written below `.agent-state/agents-messaging/debug-sessions/`.

## Data Flow

`ui_debug_request` payloads are intentionally small. Full logs, network records,
and screenshots are files. Reply messages include counts, the first errors, and
artifact paths.
