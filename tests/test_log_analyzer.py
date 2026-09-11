from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_source_package(package_name: str, package_dir: Path) -> None:
    if package_name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        package_name,
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


def load_analyzer_module():
    module_name = "test_agent_logs_analyzer"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "agent-config" / "agents" / "agent-logs-analyzer" / "log_analyzer.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


load_source_package("agent_monorepo", ROOT / "agent-runtime" / "agent-monorepo")
ANALYZER = load_analyzer_module()


class LogAnalyzerTests(unittest.TestCase):
    def tearDown(self) -> None:
        ANALYZER.stop_log_analyzer()

    def wait_for(self, predicate, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail("Timed out waiting for analyzer condition")

    def test_fresh_error_line_updates_messaging_error_and_runtime_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            try:
                state_root = project_root / ".agent-state"
                logs_root = state_root / "logs" / "system" / "runtime"
                logs_root.mkdir(parents=True)
                log_path = logs_root / "runtime.log"
                log_path.write_text(
                    "2026-09-10 INFO startup complete\n"
                    "2026-09-10 ERROR old failure should be ignored\n",
                    encoding="utf-8",
                )

                started = ANALYZER.ensure_log_analyzer_running(
                    project_root,
                    state_root,
                    poll_interval=0.05,
                )
                self.assertTrue(started)
                self.assertFalse(
                    ANALYZER.ensure_log_analyzer_running(
                        project_root,
                        state_root,
                        poll_interval=0.05,
                    )
                )

                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write("2026-09-10 INFO still fine\n")
                    handle.write("2026-09-10 ERROR FileNotFoundError: missing config.yaml\n")

                current_error_path = state_root / "agents-messaging" / "current-error.json"
                self.wait_for(current_error_path.exists)

                current_error = json.loads(current_error_path.read_text(encoding="utf-8"))
                self.assertEqual("active", current_error["status"])
                self.assertEqual(1, current_error["occurrence_count"])
                error_object = current_error["error"]
                self.assertEqual("log.error", error_object["type"])
                self.assertEqual("agent-logs-analyzer", error_object["source"])
                self.assertEqual(str(log_path.relative_to(project_root)), error_object["log_path"])
                self.assertEqual(4, error_object["line_number"])
                self.assertEqual(
                    "2026-09-10 ERROR FileNotFoundError: missing config.yaml",
                    error_object["line"],
                )
                self.assertIn("4: 2026-09-10 ERROR FileNotFoundError: missing config.yaml", error_object["context"])
                self.assertFalse((project_root / "system-issues").exists())

                message_records = list((state_root / "agents-messaging" / "records" / "messages").glob("*.json"))
                self.assertEqual(1, len(message_records))
                message_record = json.loads(message_records[0].read_text(encoding="utf-8"))
                self.assertEqual("error.detected", message_record["type"])
                self.assertEqual(error_object, message_record["payload"])

                run_id = f"log-analyzer-{datetime.now(timezone.utc).date().isoformat()}"
                events_path = (
                    project_root
                    / ".agent-state"
                    / "logs"
                    / "system-log-analyzer"
                    / run_id
                    / "events.jsonl"
                )

                def has_error_event() -> bool:
                    if not events_path.exists():
                        return False
                    events = [
                        json.loads(line)
                        for line in events_path.read_text(encoding="utf-8").splitlines()
                    ]
                    return any(event["type"] == "error" for event in events)

                self.wait_for(has_error_event)
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                ]
                self.assertIn("background.started", [event["type"] for event in events])
                error_event = next(event for event in events if event["type"] == "error")
                self.assertEqual("agent-logs-analyzer", error_event["agent_id"])
                self.assertEqual("detected", error_event["status"])
                self.assertEqual(4, error_event["payload"]["error"]["line_number"])
                self.assertEqual(
                    str(current_error_path.resolve()),
                    error_event["payload"]["current_error_path"],
                )
            finally:
                ANALYZER.stop_log_analyzer(project_root)

    def test_build_log_error_object_preserves_line_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            log_path = project_root / ".agent-state" / "logs" / "system" / "runtime" / "runtime.log"
            log_path.parent.mkdir(parents=True)
            finding = ANALYZER.build_log_error_object(
                project_root,
                log_path,
                7,
                "2026-09-10 ERROR asyncio.exceptions.CancelledError",
                ["7: 2026-09-10 ERROR asyncio.exceptions.CancelledError"],
            )

        self.assertEqual("log.error", finding["type"])
        self.assertEqual(str(log_path.relative_to(project_root)), finding["log_path"])
        self.assertEqual(7, finding["line_number"])
        self.assertEqual("2026-09-10 ERROR asyncio.exceptions.CancelledError", finding["line"])
        self.assertEqual(["7: 2026-09-10 ERROR asyncio.exceptions.CancelledError"], finding["context"])


if __name__ == "__main__":
    unittest.main()
