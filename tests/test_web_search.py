from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOL_DIRECTORY = ROOT / "agent-tools" / "web-search"
SERVICE = TOOL_DIRECTORY / "service.py"


def load_web_search_module(name: str, path: Path):
    """Load a standalone web-search module for focused unit tests."""
    if str(TOOL_DIRECTORY) not in sys.path:
        sys.path.insert(0, str(TOOL_DIRECTORY))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WebSearchTests(unittest.TestCase):
    def test_prompt_contains_request(self) -> None:
        """Keep Codex research prompts explicit and bounded."""
        module = load_web_search_module("web_search_service_prompt", SERVICE)
        request = sys.modules["model"].SearchRequest("What changed?")
        prompt = module.build_search_prompt(request)
        self.assertIn("Research request:\nWhat changed?", prompt)

    def test_save_markdown_persists_response(self) -> None:
        """Persist a Codex response without browser-specific artifacts."""
        module = load_web_search_module("web_search_service_markdown", SERVICE)
        response = {
            "query": "Question",
            "answer": "Answer",
            "sources": [
                {"title": "Example", "url": "https://example.com", "summary": "Evidence."}
            ],
        }
        with TemporaryDirectory() as directory:
            path = module.save_markdown(response, directory)
            self.assertTrue(path.exists())
            saved = path.read_text(encoding="utf-8")
            self.assertIn("# Web Search Result", saved)
            self.assertIn("[Example](https://example.com)", saved)

    def test_search_returns_agent_friendly_json(self) -> None:
        """Return validated structured data without calling a live Codex service."""
        module = load_web_search_module("web_search_service_result", SERVICE)
        request = sys.modules["model"].SearchRequest("What changed?")

        class FakeClient:
            """Small context-managed replacement for the shared SDK client."""

            def __init__(self, *args: object, **kwargs: object) -> None:
                """Accept the service's client configuration."""

            def __enter__(self):
                """Return the fake client context."""
                return self

            def __exit__(self, *args: object) -> None:
                """Close the fake client context."""

            def run_structured(self, *args: object, **kwargs: object) -> dict:
                """Return a deterministic structured research result."""
                return {
                    "answer": "A structured answer.",
                    "sources": [
                        {
                            "title": "Primary source",
                            "url": "https://example.com/source",
                            "summary": "Supporting evidence.",
                        }
                    ],
                }

        with patch.object(module, "CodexSDKClient", FakeClient):
            response = module.search(request)

        self.assertEqual("What changed?", response["query"])
        self.assertEqual("A structured answer.", response["answer"])
        self.assertEqual("https://example.com/source", response["sources"][0]["url"])


if __name__ == "__main__":
    unittest.main()
