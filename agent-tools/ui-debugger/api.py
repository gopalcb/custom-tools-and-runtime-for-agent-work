"""Provide a debugger-facing proxy to the local Codex SDK API.

This module does not run Codex itself. It calls the SDK client's HTTP endpoints
and keeps the debugger contract stable for the Nest controller and local tools.
"""

from __future__ import annotations

import json
import os
import argparse
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, request, stream_with_context


DEFAULT_CODEX_API_URL = "http://127.0.0.1:8770"


class CodexDebuggerApi:
    """Call the Codex SDK API from the debugger integration boundary."""

    def __init__(self, codex_api_url: str) -> None:
        """Store the SDK API base URL without a trailing slash."""
        self.codex_api_url = codex_api_url.rstrip("/")

    def request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        """Call a JSON SDK endpoint and return its JSON object response."""
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_value = Request(
            f"{self.codex_api_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        try:
            with urlopen(request_value, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ValueError(detail or f"Codex SDK API returned HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"Codex SDK API is unavailable: {error.reason}") from error
        if not isinstance(value, dict):
            raise ValueError("Codex SDK API returned a non-object JSON response")
        return value

    def stream_turn(self, turn_id: str) -> Iterator[str]:
        """Yield raw NDJSON lines from the SDK stream until its turn ends."""
        request_value = Request(f"{self.codex_api_url}/v1/turns/{turn_id}/stream")
        try:
            with urlopen(request_value, timeout=300) as response:
                for line in response:
                    decoded = line.decode("utf-8").strip()
                    if decoded:
                        yield decoded
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ValueError(detail or f"Codex SDK API returned HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"Codex SDK API is unavailable: {error.reason}") from error


def create_app(codex_api_url: str | None = None) -> Flask:
    """Create the debugger API that internally delegates to Codex SDK routes."""
    app = Flask(__name__)
    app.extensions["codex_debugger_api"] = CodexDebuggerApi(
        codex_api_url or os.environ.get("CODEX_SDK_API_URL", DEFAULT_CODEX_API_URL)
    )

    def service() -> CodexDebuggerApi:
        """Return the configured Codex SDK API proxy."""
        return app.extensions["codex_debugger_api"]

    @app.get("/health")
    def health() -> Any:
        """Report the downstream Codex SDK API health."""
        return jsonify(service().request_json("GET", "/health"))

    @app.post("/v1/turns")
    def start_turn() -> Any:
        """Create a streaming SDK turn through the local Codex client."""
        return jsonify(service().request_json("POST", "/v1/turns", request.get_json(silent=True) or {})), 202

    @app.get("/v1/turns/<turn_id>/stream")
    def stream_turn(turn_id: str) -> Response:
        """Proxy raw SDK event logs for one active turn."""
        return Response(
            stream_with_context((line + "\n" for line in service().stream_turn(turn_id))),
            mimetype="application/x-ndjson",
        )

    @app.post("/v1/turns/<turn_id>/steer")
    def steer_turn(turn_id: str) -> Any:
        """Forward user steering input to the active SDK turn."""
        return jsonify(service().request_json("POST", f"/v1/turns/{turn_id}/steer", request.get_json(silent=True) or {}))

    @app.post("/v1/turns/<turn_id>/interrupt")
    def interrupt_turn(turn_id: str) -> Any:
        """Forward an interruption request to the active SDK turn."""
        return jsonify(service().request_json("POST", f"/v1/turns/{turn_id}/interrupt", request.get_json(silent=True) or {}))

    @app.errorhandler(ValueError)
    @app.errorhandler(RuntimeError)
    def downstream_error(error: Exception) -> Any:
        """Translate a downstream service error into a useful gateway response."""
        return jsonify({"error": str(error)}), 502

    return app


def main() -> None:
    """Run the local debugger API proxy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--codex-api-url", default=None)
    args = parser.parse_args()
    create_app(args.codex_api_url).run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
