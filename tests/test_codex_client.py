from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[1]


def _load_source_package() -> None:
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


_load_source_package()

from agent_monorepo.codex_client import CodexAppServerClient


class CodexClientApprovalTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, **kwargs) -> CodexAppServerClient:
        return CodexAppServerClient(cwd=ROOT, **kwargs)

    @staticmethod
    def _capture_sends(client: CodexAppServerClient) -> list[dict[str, object]]:
        sent: list[dict[str, object]] = []

        async def send(value) -> None:
            sent.append(dict(value))

        client._send = send
        return sent

    async def test_never_policy_auto_accepts_and_surfaces_normalized_request(self) -> None:
        client = self._client()
        sent = self._capture_sends(client)

        await client._handle_server_request(
            {
                "id": 41,
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "pytest"},
            }
        )

        self.assertEqual([{"id": 41, "result": {"decision": "accept"}}], sent)
        self.assertEqual(
            {
                "method": "client/approval/requested",
                "params": {
                    "requestId": 41,
                    "requestMethod": "item/commandExecution/requestApproval",
                    "request": {"command": "pytest"},
                    "approvalPolicy": "never",
                    "status": "accepted",
                },
            },
            client._messages.get_nowait(),
        )

    async def test_opt_in_policy_waits_for_public_client_decision(self) -> None:
        client = self._client(approval_policy="on-request")
        sent = self._capture_sends(client)
        handling = asyncio.create_task(
            client._handle_server_request(
                {
                    "id": 42,
                    "method": "item/fileChange/requestApproval",
                    "params": {"path": "result.txt"},
                }
            )
        )

        request = await asyncio.wait_for(client._messages.get(), 0.5)
        self.assertEqual(42, request["params"]["requestId"])
        self.assertEqual("pending", request["params"]["status"])
        self.assertEqual("on-request", request["params"]["approvalPolicy"])
        self.assertFalse(handling.done())

        await client.respond_to_approval(42, "decline")
        await asyncio.wait_for(handling, 0.5)

        self.assertEqual([{"id": 42, "result": {"decision": "decline"}}], sent)

    async def test_opt_in_policy_can_use_async_approval_handler(self) -> None:
        requests: list[dict[str, object]] = []

        async def decide(request: dict[str, object]) -> str:
            requests.append(request)
            return "acceptForSession"

        client = self._client(approval_policy="on-request", approval_handler=decide)
        sent = self._capture_sends(client)

        await client._handle_server_request(
            {"id": 43, "method": "item/commandExecution/requestApproval", "params": {}}
        )

        self.assertEqual("client/approval/requested", requests[0]["method"])
        self.assertEqual(
            [{"id": 43, "result": {"decision": "acceptForSession"}}], sent
        )

    async def test_models_command_uses_structured_model_list_request(self) -> None:
        client = self._client()
        client.request = AsyncMock(return_value={"models": [{"id": "codex-local"}]})
        client.start = AsyncMock()

        result = await client.run_command("/models")

        self.assertEqual("/models", result["command"])
        self.assertEqual("codex-local", result["models"][0]["id"])
        client.request.assert_awaited_once_with("model/list", {})
        client.start.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
