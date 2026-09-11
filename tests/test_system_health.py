from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_monorepo.system_health import run_monorepo_system_health
from agents_internal_messaging import MessageBus


class SystemHealthTests(unittest.TestCase):
    def test_health_check_creates_required_state_and_reports_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "project-registry.yaml").write_text("version: 1\n", encoding="utf-8")
            (root / "agent-config" / "agents").mkdir(parents=True)

            result = run_monorepo_system_health(root)

            self.assertEqual("healthy", result["status"])
            self.assertTrue((root / ".agent-state" / "logs" / "system" / "health" / "latest.json").is_file())
            self.assertTrue((root / ".agent-state" / "agents-messaging" / "errors").is_dir())
            self.assertIsNone(MessageBus(root / ".agent-state" / "agents-messaging").read_current_error())

    def test_unhealthy_check_records_current_error_for_messaging_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            result = run_monorepo_system_health(root)

            self.assertEqual("unhealthy", result["status"])
            current_error_path = root / ".agent-state" / "agents-messaging" / "current-error.json"
            self.assertTrue(current_error_path.is_file())
            current_error = json.loads(current_error_path.read_text(encoding="utf-8"))
            self.assertEqual("active", current_error["status"])
            self.assertEqual("monorepo_system_health.failed", current_error["error"]["type"])
            failed_checks = current_error["error"]["checks"]
            self.assertTrue(any(check["name"] == "project-registry" for check in failed_checks))


if __name__ == "__main__":
    unittest.main()
