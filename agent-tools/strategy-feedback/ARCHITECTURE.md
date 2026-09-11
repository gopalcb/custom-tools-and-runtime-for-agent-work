# Architecture

## Purpose

The strategy feedback tool opens a small desktop form after agent work so the
runtime can capture user feedback, optional rework requests, and the user's
choice about durable work-memory storage.

## Main Flow

`strategy_feedback_gui.py` receives the current run id, session id, and output
path from the runtime. It opens a Tkinter form with feedback fields, a default
checked memory checkbox, Submit, and Cancel. Submit writes a `submitted` JSON
payload. Cancel or window close writes a `cancelled` payload. Headless Tkinter
startup failures write an `unavailable` payload so the runtime can finish
without hanging.

## Module Responsibilities

- `strategy_feedback_gui.py`: CLI entry point and Tkinter form implementation.
  It owns only feedback collection and JSON response writing. Runtime analysis,
  rework, event emission, and memory storage remain in
  `agent-runtime/agent-monorepo/`.

## Configuration

The runtime controls whether this tool runs through
`memory.strategy_feedback.enabled` in `project-registry.yaml`.
