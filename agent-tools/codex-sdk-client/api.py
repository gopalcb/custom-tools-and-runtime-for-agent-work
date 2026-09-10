"""Expose the shared Codex SDK façade through a small local Flask API.

The stream endpoint preserves each SDK notification as JSON so a UI can render
the same agent activity that Codex emits without scraping a terminal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, stream_with_context

from agent_monorepo.codex_client import CodexSDKClient


class CodexApiService:
    """Own SDK clients and active turn handles for one local API process."""

    def __init__(self, cwd: str | Path) -> None:
        """Create a service scoped to a repository working directory."""
        self.cwd = Path(cwd).expanduser().resolve()
        self.client = CodexSDKClient(self.cwd)
        self.threads: dict[str, Any] = {}
        self.turns: dict[str, Any] = {}

    def start_turn(self, payload: dict[str, Any]) -> dict[str, str]:
        """Start a controllable SDK turn and return its identifiers."""
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        sandbox = str(payload.get("sandbox", "workspace_write"))
        thread_id, handle = self.client.start_turn(
            prompt,
            thread_id=str(payload["thread_id"]) if payload.get("thread_id") else None,
            sandbox=sandbox,
            model=payload.get("model"),
            ephemeral=bool(payload.get("ephemeral", False)),
        )
        turn_id = str(handle.id)
        self.threads[thread_id] = handle
        self.turns[turn_id] = handle
        return {"thread_id": thread_id, "turn_id": turn_id}

    def collect_turn(self, turn_id: str) -> dict[str, Any]:
        """Collect a turn normally and return its final text."""
        handle = self.turns.get(turn_id)
        if handle is None:
            raise KeyError(f"Unknown turn: {turn_id}")
        result = handle.run()
        return {
            "turn_id": result.id,
            "status": str(result.status),
            "text": result.final_response or "",
            "events": [],
        }

    def steer_turn(self, turn_id: str, prompt: str) -> None:
        """Send additional user input to an active SDK turn."""
        handle = self.turns.get(turn_id)
        if handle is None:
            raise KeyError(f"Unknown turn: {turn_id}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        handle.steer(prompt)

    def interrupt_turn(self, turn_id: str) -> None:
        """Interrupt an active SDK turn."""
        handle = self.turns.get(turn_id)
        if handle is None:
            raise KeyError(f"Unknown turn: {turn_id}")
        handle.interrupt()

    def close(self) -> None:
        """Close the underlying SDK runtime."""
        self.client.close()


def serialize_sdk_event(event: Any) -> dict[str, Any]:
    """Convert one SDK notification to the JSON object exposed by the stream."""
    if hasattr(event, "model_dump"):
        value = event.model_dump(mode="json")
    elif isinstance(event, dict):
        value = event
    else:
        value = {"type": type(event).__name__, "message": str(event)}
    if not isinstance(value, dict):
        return {"type": type(event).__name__, "value": value}
    return value


def create_app(cwd: str | Path = ".", service: CodexApiService | None = None) -> Flask:
    """Create the local API application with an injectable service."""
    app = Flask(__name__)
    app.extensions["codex_api_service"] = service or CodexApiService(cwd)

    @app.get("/health")
    def health() -> Any:
        """Report that the API process is available."""
        return jsonify({"status": "ok"})

    @app.errorhandler(KeyError)
    @app.errorhandler(ValueError)
    def bad_request(error: Exception) -> Any:
        """Return caller mistakes as stable JSON errors."""
        return jsonify({"error": str(error)}), 400

    @app.post("/v1/run/text")
    def run_text() -> Any:
        """Run one non-streaming SDK text turn."""
        payload = request.get_json(silent=True) or {}
        service_instance = app.extensions["codex_api_service"]
        result = service_instance.client.run_text(**payload)
        return jsonify({
            "text": result.text,
            "thread_id": result.thread_id,
            "turn_id": result.turn_id,
            "status": result.status,
        })

    @app.post("/v1/run/structured")
    def run_structured() -> Any:
        """Run one SDK turn with a JSON output schema."""
        payload = request.get_json(silent=True) or {}
        schema = payload.pop("output_schema", None)
        if not isinstance(schema, dict):
            return jsonify({"error": "output_schema must be an object"}), 400
        service_instance = app.extensions["codex_api_service"]
        return jsonify(service_instance.client.run_structured(**payload, output_schema=schema))

    @app.post("/v1/turns")
    def start_turn() -> Any:
        """Start a controllable streaming-capable SDK turn."""
        service_instance = app.extensions["codex_api_service"]
        return jsonify(service_instance.start_turn(request.get_json(silent=True) or {})), 202

    @app.get("/v1/turns/<turn_id>")
    def collect_turn(turn_id: str) -> Any:
        """Collect streamed events and the completed turn result."""
        service_instance = app.extensions["codex_api_service"]
        return jsonify(service_instance.collect_turn(turn_id))

    @app.get("/v1/turns/<turn_id>/stream")
    def stream_turn(turn_id: str) -> Response:
        """Stream SDK notifications as newline-delimited JSON."""
        service_instance = app.extensions["codex_api_service"]
        handle = service_instance.turns.get(turn_id)
        if handle is None:
            return Response(json.dumps({"error": f"Unknown turn: {turn_id}"}), status=404)

        def events() -> Any:
            """Yield one JSON event for each SDK notification."""
            for event in handle.stream():
                yield json.dumps(serialize_sdk_event(event), ensure_ascii=False) + "\n"

        return Response(stream_with_context(events()), mimetype="application/x-ndjson")

    @app.post("/v1/turns/<turn_id>/steer")
    def steer_turn(turn_id: str) -> Any:
        """Steer an active turn with additional input."""
        service_instance = app.extensions["codex_api_service"]
        service_instance.steer_turn(turn_id, (request.get_json(silent=True) or {}).get("prompt", ""))
        return jsonify({"status": "steered", "turn_id": turn_id})

    @app.post("/v1/turns/<turn_id>/interrupt")
    def interrupt_turn(turn_id: str) -> Any:
        """Interrupt an active turn."""
        service_instance = app.extensions["codex_api_service"]
        service_instance.interrupt_turn(turn_id)
        return jsonify({"status": "interrupt requested", "turn_id": turn_id})

    return app


def main() -> None:
    """Run the local API server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=".", help="Repository working directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    app = create_app(args.cwd)
    try:
        app.run(host=args.host, port=args.port, debug=False)
    finally:
        app.extensions["codex_api_service"].close()


if __name__ == "__main__":
    main()
