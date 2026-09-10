from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from agents_internal_messaging import AgentMessage, MessageBus


class BusTests(unittest.TestCase):
    def test_send_read_and_mark_processed(self):
        with TemporaryDirectory() as temp_dir:
            bus = MessageBus(temp_dir)
            message = AgentMessage(
                sender="builder-agent",
                recipient="angular-ui-debugger-agent",
                type="ui_debug_request",
                payload={"url": "http://localhost:4200", "artifacts": ["screenshot"]},
            )

            path = bus.send(message)
            self.assertTrue(path.exists())
            self.assertEqual(bus.pending("angular-ui-debugger-agent"), [path])
            self.assertEqual(bus.summary()["by_status"], {"pending": 1})

            loaded = bus.read(path)
            self.assertEqual(loaded.sender, "builder-agent")
            self.assertEqual(loaded.payload["artifacts"], ["screenshot"])
            self.assertEqual(bus.read_record(loaded.id).status, "pending")

            processed = bus.mark_processed("angular-ui-debugger-agent", path)
            self.assertTrue(processed.exists())
            self.assertEqual(bus.pending("angular-ui-debugger-agent"), [])
            self.assertEqual(bus.read_record(loaded.id).status, "processed")
            self.assertTrue((bus.records_dir() / "events.jsonl").exists())

    def test_list_records_includes_failed_and_threads_replies(self):
        with TemporaryDirectory() as temp_dir:
            bus = MessageBus(temp_dir)
            request = AgentMessage(
                sender="builder-agent",
                recipient="review-agent",
                type="review_request",
                payload={"scope": ["src/app"]},
            )
            request_path = bus.send(request)
            bus.mark_failed("review-agent", request_path, "missing handler")
            reply = AgentMessage(
                sender="review-agent",
                recipient="builder-agent",
                type="review_request.result",
                payload={"ok": False},
                reply_to=request.id,
            )
            bus.send(reply)

            records = bus.list_records(agent_id="builder-agent")
            self.assertEqual({record.message.id for record in records}, {request.id, reply.id})
            self.assertEqual(bus.read_record(request.id).error, "missing handler")
            self.assertEqual([record.message.id for record in bus.thread(request.id)], [request.id, reply.id])


if __name__ == "__main__":
    unittest.main()
