"""Verify App Server notifications become stable runtime events."""

from __future__ import annotations

from agent_monorepo.runtime import AgentRuntime
import unittest


def normalize(method: str, params: dict):
    """Normalize one synthetic App Server notification."""
    return AgentRuntime._normalize_codex({"method": method, "params": params})


class CodexNormalizationTests(unittest.TestCase):
    """Cover the stable payloads consumed by runtime clients."""

    def test_supported_notifications_use_flat_stable_payloads(self) -> None:
        command = {
            "id": "command-1", "type": "commandExecution", "command": "pytest -q",
            "cwd": "/repo", "status": "completed", "aggregatedOutput": "2 passed\n",
            "exitCode": 0, "durationMs": 120,
        }
        started = normalize("item/started", {"item": command})[0]
        progress = normalize("item/commandExecution/outputDelta", {"itemId": "command-1", "delta": "1 passed\n"})[0]
        completed = normalize("item/completed", {"item": command})[0]
        self.assertEqual({"tool": "shell", "tool_id": "command-1", "command": "pytest -q", "cwd": "/repo", "status": "completed"}, started[2])
        self.assertEqual("tool.progress", progress[0])
        self.assertEqual("1 passed\n", progress[2]["output"])
        self.assertEqual("tool.completed", completed[0])
        self.assertEqual(0, completed[2]["exit_code"])
        self.assertNotIn("item", completed[2])

        file_events = normalize("item/completed", {"item": {"id": "patch-1", "type": "fileChange", "status": "completed", "changes": [{"path": "src/app.py", "kind": "add", "diff": "+print('ok')\n"}]}})
        self.assertEqual({"file_id": "patch-1", "path": "src/app.py", "kind": "add", "diff": "+print('ok')\n"}, file_events[0][2])
        self.assertEqual("artifact.created", file_events[1][0])

        patch = normalize("item/fileChange/patchUpdated", {"itemId": "patch-1", "path": "src/app.py", "patch": "+live\n"})[0]
        self.assertEqual("file.changed", patch[0])
        self.assertEqual("src/app.py", patch[2]["path"])

    def test_usage_and_messages_are_normalized_for_sse_consumers(self) -> None:
        message = normalize("item/agentMessage/delta", {"delta": "Hello"})[0]
        self.assertEqual(("agent.message.delta", "Hello", {"delta": "Hello"}), message)
        usage = normalize("thread/tokenUsage/updated", {"tokenUsage": {"total": {"inputTokens": 40, "cachedInputTokens": 10, "outputTokens": 12, "reasoningOutputTokens": 3, "totalTokens": 52}, "last": {"inputTokens": 8}, "modelContextWindow": 200000}})[0]
        self.assertEqual("agent.usage.updated", usage[0])
        self.assertEqual(52, usage[2]["total_tokens"])
        self.assertEqual(200000, usage[2]["context_window"])


if __name__ == "__main__":
    unittest.main()
