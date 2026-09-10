from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_runtime_package() -> None:
    """Load the source runtime package for tests that do not install it."""
    if "agent_monorepo" in sys.modules:
        return
    package_dir = ROOT / "agent-runtime" / "agent-monorepo"
    spec = importlib.util.spec_from_file_location(
        "agent_monorepo",
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


load_runtime_package()

from agent_monorepo import codex_client


class FakeResult:
    """Minimal SDK turn result used by façade tests."""

    id = "turn-1"
    status = "completed"
    final_response = json.dumps({"ok": True})
    usage = None


class FakeThread:
    """Minimal SDK thread used by façade tests."""

    id = "thread-1"

    def run(self, prompt: str, **kwargs: object) -> FakeResult:
        """Return a deterministic fake result."""
        return FakeResult()


class FakeCodex:
    """Minimal SDK client used by façade tests."""

    def __init__(self, config: object) -> None:
        self.config = config

    def thread_start(self, **kwargs: object) -> FakeThread:
        """Create a fake new thread."""
        return FakeThread()

    def close(self) -> None:
        """Close the fake client."""


class CodexSDKClientTests(unittest.TestCase):
    """Verify SDK façade normalization without launching Codex."""

    def test_run_text_normalizes_sdk_result(self) -> None:
        """Return text and identifiers from the SDK's native result."""
        with patch.object(codex_client, "Codex", FakeCodex):
            client = codex_client.CodexSDKClient(ROOT)
            result = client.run_text("hello")
            client.close()

        self.assertEqual("thread-1", result.thread_id)
        self.assertEqual("turn-1", result.turn_id)
        self.assertEqual('{"ok": true}', result.text)

    def test_run_structured_parses_json(self) -> None:
        """Parse SDK structured output into a dictionary."""
        with patch.object(codex_client, "Codex", FakeCodex):
            with codex_client.CodexSDKClient(ROOT) as client:
                result = client.run_structured("plan", {"type": "object"})

        self.assertEqual({"ok": True}, result)

    def test_sandbox_names_and_native_binary_validation(self) -> None:
        """Support documented sandbox names and clear native-binary failures."""
        self.assertEqual(codex_client.Sandbox.read_only, codex_client.CodexSDKClient.sandbox("read_only"))
        with patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "was not found"):
                codex_client.CodexSDKClient.resolve_native_codex()


if __name__ == "__main__":
    unittest.main()
