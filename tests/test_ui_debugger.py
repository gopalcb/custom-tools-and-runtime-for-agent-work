from __future__ import annotations

import json
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ui_debugger import runner
from ui_debugger.runner import DebugRequest, collect_network_errors, run_debug_request


def performance_event(method: str, params: dict) -> dict:
    return {"message": json.dumps({"message": {"method": method, "params": params}})}


class UiDebuggerTests(unittest.TestCase):
    def test_network_filter_keeps_actual_xhr_and_document_failures(self):
        entries = [
            performance_event(
                "Network.requestWillBeSent",
                {"requestId": "ok-css", "type": "Stylesheet", "request": {"url": "http://local/style.css", "method": "GET"}},
            ),
            performance_event(
                "Network.responseReceived",
                {"requestId": "ok-css", "type": "Stylesheet", "response": {"url": "http://local/style.css", "status": 404}},
            ),
            performance_event(
                "Network.requestWillBeSent",
                {"requestId": "xhr", "type": "XHR", "request": {"url": "http://local/api/tasks", "method": "GET"}},
            ),
            performance_event(
                "Network.responseReceived",
                {"requestId": "xhr", "type": "XHR", "response": {"url": "http://local/api/tasks", "status": 500}},
            ),
            performance_event(
                "Network.requestWillBeSent",
                {"requestId": "doc", "type": "Document", "request": {"url": "http://local/missing", "method": "GET"}},
            ),
            performance_event(
                "Network.loadingFailed",
                {"requestId": "doc", "type": "Document", "errorText": "net::ERR_CONNECTION_REFUSED"},
            ),
        ]

        errors = collect_network_errors(entries)

        self.assertEqual(2, len(errors))
        self.assertEqual(["http", "network"], [error["type"] for error in errors])
        self.assertEqual("http://local/api/tasks", errors[0]["url"])

    def test_missing_selenium_writes_actionable_manifest(self):
        with TemporaryDirectory() as temp_dir:
            request = DebugRequest.from_dict(
                {
                    "url": "http://127.0.0.1:9",
                    "request_id": "unit-test",
                    "artifact_root": temp_dir,
                }
            )
            with patch.object(runner, "webdriver", None), patch.object(runner, "ChromeOptions", None):
                result = run_debug_request(request)

            self.assertTrue(result.manifest_path.exists())
            self.assertEqual("unit-test", result.request_id)
            self.assertIn("artifact_paths", result.summary)


if __name__ == "__main__":
    unittest.main()
