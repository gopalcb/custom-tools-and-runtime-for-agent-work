from __future__ import annotations

import contextlib
import io
import json
import unittest
from tempfile import TemporaryDirectory

from agents_internal_messaging.cli import main


class CliTests(unittest.TestCase):
    def test_list_json_exposes_visible_message_records(self):
        with TemporaryDirectory() as temp_dir:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--root",
                            temp_dir,
                            "send",
                            "--sender",
                            "builder-agent",
                            "--recipient",
                            "review-agent",
                            "--type",
                            "review_request",
                            "--payload-json",
                            '{"scope": ["src/app"]}',
                        ]
                    ),
                    0,
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--root", temp_dir, "list", "--json"]), 0)

            records = json.loads(output.getvalue())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["sender"], "builder-agent")
            self.assertEqual(records[0]["recipient"], "review-agent")
            self.assertEqual(records[0]["status"], "pending")
            self.assertEqual(records[0]["payload"], {"scope": ["src/app"]})

    def test_error_commands_show_and_resolve_current_error(self):
        with TemporaryDirectory() as temp_dir:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--root",
                            temp_dir,
                            "send",
                            "--sender",
                            "agent-error-monitor",
                            "--recipient",
                            "agent-logs-analyzer",
                            "--type",
                            "error.detected",
                            "--payload-json",
                            '{"type": "manual.error"}',
                        ]
                    ),
                    0,
                )

            from agents_internal_messaging import MessageBus

            bus = MessageBus(temp_dir)
            bus.record_error({"type": "manual.error", "message": "boom"})

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--root", temp_dir, "current-error", "--json"]), 0)
            current = json.loads(output.getvalue())
            self.assertEqual("active", current["status"])

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--root",
                            temp_dir,
                            "resolve-error",
                            "--details-json",
                            '{"confirmed_by": "test"}',
                        ]
                    ),
                    0,
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--root", temp_dir, "errors", "--json"]), 0)
            archived = json.loads(output.getvalue())
            self.assertEqual("fixed", archived[0]["status"])
            self.assertEqual({"confirmed_by": "test"}, archived[0]["resolution"])


if __name__ == "__main__":
    unittest.main()
