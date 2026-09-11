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
            self.assertTrue(bus.manifest_path().exists())
            sent_event = bus.read_events(limit=1)[0]
            self.assertEqual(sent_event["event"], "sent")
            self.assertEqual(sent_event["payload"], message.payload)

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

    def test_task_records_are_visible_in_summary(self):
        with TemporaryDirectory() as temp_dir:
            bus = MessageBus(temp_dir)
            bus.write_task_record(
                {
                    "id": "task-1",
                    "title": "Debug the controller",
                    "status": "awaiting implementation",
                    "agent_id": "agent-ui-debugger",
                }
            )

            bus.update_task_status("task-1", "implementing", "Agent accepted task")

            tasks = bus.list_task_records()
            self.assertEqual(1, len(tasks))
            self.assertEqual("implementing", tasks[0]["status"])
            self.assertEqual({"implementing": 1}, bus.summary()["task_statuses"])

    def test_error_tracking_keeps_current_error_until_resolved(self):
        with TemporaryDirectory() as temp_dir:
            bus = MessageBus(temp_dir)
            error = {
                "type": "runtime.error",
                "message": "Validation command failed",
                "payload": {"exit_code": 1},
            }

            first = bus.record_error(error)
            second = bus.record_error(error)

            self.assertEqual(first["fingerprint"], second["fingerprint"])
            self.assertEqual(2, second["occurrence_count"])
            self.assertEqual(second, bus.read_current_error())
            self.assertEqual(1, bus.summary()["active_errors"])
            message = bus.list_records(message_type="error.detected")[0]
            self.assertEqual(error, message.message.payload)

            resolved = bus.resolve_current_error(details={"validated_by": "pytest"})

            self.assertEqual("fixed", resolved["status"])
            self.assertIsNone(bus.read_current_error())
            self.assertEqual(0, bus.summary()["active_errors"])
            archived = bus.list_error_records()
            self.assertEqual(1, len(archived))
            self.assertEqual("fixed", archived[0]["status"])
            self.assertEqual({"validated_by": "pytest"}, archived[0]["resolution"])


if __name__ == "__main__":
    unittest.main()
