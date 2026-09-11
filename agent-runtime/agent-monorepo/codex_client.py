"""Structured client for the Codex App Server protocol."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from openai_codex import Codex, CodexConfig, Sandbox
except ImportError as error:  # The App Server adapter remains importable without the SDK.
    Codex = None
    CodexConfig = None
    Sandbox = None
    CODEX_SDK_IMPORT_ERROR = error
else:
    CODEX_SDK_IMPORT_ERROR = None


logger = logging.getLogger(__name__)


class CodexProtocolError(RuntimeError):
    """Raised when App Server cannot satisfy its structured protocol."""


@dataclass(slots=True)
class CodexRunResult:
    """Normalized result returned by the official Codex SDK façade."""

    text: str
    thread_id: str
    turn_id: str
    status: str
    usage: Any | None = None


class CodexSDKClient:
    """Thin synchronous façade over the official ``openai_codex`` SDK."""

    def __init__(
        self,
        cwd: str | Path,
        use_native_codex: bool = False,
        model: str | None = None,
        approval_mode: Any | None = None,
    ) -> None:
        """Configure a repository-scoped SDK client without owning protocol code."""
        if Codex is None or CodexConfig is None or Sandbox is None:
            raise RuntimeError(
                "The openai-codex package is required for the SDK client."
            ) from CODEX_SDK_IMPORT_ERROR
        self.cwd = str(Path(cwd).expanduser().resolve())
        self.model = model
        config = CodexConfig(
            codex_bin=self.resolve_native_codex() if use_native_codex else None,
            cwd=self.cwd,
            client_name="agent_monorepo",
            client_title="Agent Monorepo",
        )
        self._codex = Codex(config=config)
        self.approval_mode = approval_mode
        logger.info("Codex SDK client initialized", extra={"cwd": self.cwd, "model": self.model})

    @staticmethod
    def resolve_native_codex() -> str:
        """Return the installed Codex executable or raise an actionable error."""
        codex_bin = shutil.which("codex")
        if not codex_bin:
            raise RuntimeError(
                "Native Codex CLI was requested but 'codex' was not found."
            )
        return codex_bin

    @staticmethod
    def sandbox(value: str) -> Any:
        """Map a monorepo sandbox name to an SDK sandbox preset."""
        mapping = {
            "read_only": Sandbox.read_only,
            "read-only": Sandbox.read_only,
            "workspace_write": Sandbox.workspace_write,
            "workspace-write": Sandbox.workspace_write,
            "full_access": Sandbox.full_access,
            "full-access": Sandbox.full_access,
        }
        try:
            return mapping[value]
        except KeyError as error:
            raise ValueError(f"Unsupported Codex sandbox: {value}") from error

    def run_text(
        self,
        prompt: str,
        thread_id: str | None = None,
        sandbox: str = "read_only",
        model: str | None = None,
        developer_instructions: str | None = None,
        ephemeral: bool = True,
        effort: str | None = None,
    ) -> CodexRunResult:
        """Run a normal SDK turn on a new or resumed conversation thread."""
        options = {
            "cwd": self.cwd,
            "sandbox": self.sandbox(sandbox),
            "model": model or self.model,
            "developer_instructions": developer_instructions,
        }
        if self.approval_mode is not None:
            options["approval_mode"] = self.approval_mode
        if thread_id:
            thread = self._codex.thread_resume(thread_id, **options)
        else:
            options["ephemeral"] = ephemeral
            thread = self._codex.thread_start(**options)
        logger.info("Codex SDK text run started", extra={"thread_id": thread.id, "model": model or self.model})
        run_options = {
            "cwd": self.cwd,
            "sandbox": self.sandbox(sandbox),
            "model": model or self.model,
        }
        if effort:
            run_options["effort"] = effort
        if self.approval_mode is not None:
            run_options["approval_mode"] = self.approval_mode
        result = thread.run(prompt, **run_options)
        logger.info(
            "Codex SDK text run completed",
            extra={"thread_id": thread.id, "turn_id": result.id, "status": str(result.status)},
        )
        return CodexRunResult(
            text=result.final_response or "",
            thread_id=thread.id,
            turn_id=result.id,
            status=str(result.status),
            usage=result.usage,
        )

    def run_structured(
        self,
        prompt: str,
        output_schema: dict[str, Any],
        sandbox: str = "read_only",
        model: str | None = None,
        developer_instructions: str | None = None,
        ephemeral: bool = True,
    ) -> dict[str, Any]:
        """Run an SDK turn with a JSON schema and parse its final response."""
        result = self.run_raw(
            prompt,
            sandbox=sandbox,
            model=model,
            developer_instructions=developer_instructions,
            ephemeral=ephemeral,
            output_schema=output_schema,
        )
        if not result.final_response:
            raise RuntimeError("Codex completed without a structured final response.")
        try:
            value = json.loads(result.final_response)
        except json.JSONDecodeError as error:
            raise ValueError("Codex returned invalid structured JSON") from error
        if not isinstance(value, dict):
            raise ValueError("Codex structured output must be a JSON object")
        return value

    def run_raw(
        self,
        prompt: str,
        sandbox: str = "read_only",
        model: str | None = None,
        developer_instructions: str | None = None,
        ephemeral: bool = True,
        output_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Run one SDK turn while retaining its native result for structured callers."""
        options = {
            "cwd": self.cwd,
            "sandbox": self.sandbox(sandbox),
            "model": model or self.model,
            "developer_instructions": developer_instructions,
            "ephemeral": ephemeral,
        }
        if self.approval_mode is not None:
            options["approval_mode"] = self.approval_mode
        thread = self._codex.thread_start(**options)
        return thread.run(
            prompt,
            cwd=self.cwd,
            sandbox=self.sandbox(sandbox),
            model=model or self.model,
            output_schema=output_schema,
            **({"approval_mode": self.approval_mode} if self.approval_mode is not None else {}),
        )

    def start_turn(
        self,
        prompt: str,
        thread_id: str | None = None,
        sandbox: str = "workspace_write",
        model: str | None = None,
        ephemeral: bool = False,
    ) -> tuple[str, Any]:
        """Start an SDK turn handle for streaming, steering, or interruption."""
        options = {
            "cwd": self.cwd,
            "sandbox": self.sandbox(sandbox),
            "model": model or self.model,
        }
        if thread_id:
            thread = self._codex.thread_resume(thread_id, **options)
        else:
            thread = self._codex.thread_start(**options, ephemeral=ephemeral)
        handle = thread.turn(
            prompt,
            cwd=self.cwd,
            sandbox=self.sandbox(sandbox),
            model=model or self.model,
        )
        return thread.id, handle

    def close(self) -> None:
        """Close the SDK runtime connection."""
        self._codex.close()
        logger.info("Codex SDK client closed")

    def __enter__(self) -> "CodexSDKClient":
        """Enter the client context manager."""
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close the client when leaving its context manager."""
        self.close()


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise CodexProtocolError(f"Unable to parse Codex CLI version from: {value.strip()!r}")
    return tuple(int(part) for part in match.groups())


class CodexAppServerClient:
    """Small JSONL/JSON-RPC client for one long-lived App Server process."""

    def __init__(
        self,
        command: str | Sequence[str] = "codex app-server",
        *,
        cwd: str | Path,
        approval_policy: str = "never",
        sandbox: str = "workspace-write",
        writable_roots: Sequence[str | Path] = (),
        network_access: bool = True,
        min_version: tuple[int, int, int] = (0, 153, 4),
        max_version: tuple[int, int, int] = (0, 155, 0),
        approval_handler: Callable[[dict[str, Any]], Awaitable[str]] | None = None,
    ) -> None:
        self.command = tuple(shlex.split(command) if isinstance(command, str) else command)
        if not self.command:
            raise ValueError("Codex command cannot be empty")
        self.cwd = Path(cwd).resolve()
        self.approval_policy = approval_policy
        self.sandbox = sandbox
        self.writable_roots = tuple(Path(path).resolve() for path in writable_roots) or (self.cwd,)
        if any(path != self.cwd and self.cwd not in path.parents for path in self.writable_roots):
            raise ValueError("Codex writable roots must stay within its working directory")
        self.network_access = network_access
        self.min_version = min_version
        self.max_version = max_version
        self.approval_handler = approval_handler
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._pending_approvals: dict[int, asyncio.Future[str]] = {}
        self._messages: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._request_id = 0
        self._write_lock = asyncio.Lock()
        self._stderr: list[str] = []
        self._active_turn: tuple[str, str] | None = None
        logger.info(
            "Codex App Server client initialized",
            extra={"command": " ".join(self.command), "cwd": str(self.cwd), "sandbox": self.sandbox},
        )

    async def start(self) -> None:
        if self.process is not None:
            return
        await self.check_version()
        logger.info("Starting Codex App Server", extra={"command": " ".join(self.command), "cwd": str(self.cwd)})
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=str(self.cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agent-monorepo-runtime",
                    "title": "Codex Agent Runtime",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self.notify("initialized", {})
        logger.info("Codex App Server initialized")

    async def check_version(self) -> tuple[int, int, int]:
        logger.info("Checking Codex CLI version", extra={"command": self.command[0]})
        process = await asyncio.create_subprocess_exec(
            self.command[0],
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = (stdout + stderr).decode("utf-8", errors="replace")
        if process.returncode:
            raise CodexProtocolError(f"Unable to query Codex CLI version: {output.strip()}")
        version = _version_tuple(output)
        if not (self.min_version <= version < self.max_version):
            supported = f">={'.'.join(map(str, self.min_version))},<{'.'.join(map(str, self.max_version))}"
            raise CodexProtocolError(
                f"Unsupported Codex CLI {'.'.join(map(str, version))}; supported range is {supported}."
            )
        logger.info("Codex CLI version accepted", extra={"version": ".".join(map(str, version))})
        return version

    async def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        await self._ensure_running()
        self._request_id += 1
        request_id = self._request_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send({"id": request_id, "method": method, "params": dict(params)})
        try:
            response = await future
        finally:
            self._pending.pop(request_id, None)
        if "error" in response:
            error = response["error"]
            message = error.get("message", error) if isinstance(error, dict) else error
            logger.error("Codex App Server request failed", extra={"method": method, "request_id": request_id})
            raise CodexProtocolError(f"{method} failed: {message}")
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise CodexProtocolError(f"{method} returned a non-object result")
        logger.info("Codex App Server request completed", extra={"method": method, "request_id": request_id})
        return result

    async def notify(self, method: str, params: Mapping[str, Any]) -> None:
        await self._ensure_running()
        await self._send({"method": method, "params": dict(params)})

    async def stream_turn(
        self,
        prompt: str,
        *,
        developer_instructions: str,
        model: str | None = None,
        effort: str | None = None,
        thread_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        await self.start()
        thread_params: dict[str, Any] = {
            "cwd": str(self.cwd),
            "developerInstructions": developer_instructions,
            "approvalPolicy": self.approval_policy,
            "sandbox": self._sandbox_wire_value(),
        }
        if model:
            thread_params["model"] = model
        if thread_id:
            result = await self.request("thread/resume", {"threadId": thread_id, **thread_params})
        else:
            result = await self.request("thread/start", thread_params)
        thread = result.get("thread") or {}
        active_thread_id = thread.get("id")
        if not active_thread_id:
            raise CodexProtocolError("App Server did not return a thread id")
        logger.info(
            "Codex turn starting",
            extra={
                "thread_id": active_thread_id,
                "resumed": bool(thread_id),
                "model": model,
                "effort": effort,
            },
        )
        turn_params = {
            "threadId": active_thread_id,
            "input": [{"type": "text", "text": prompt}],
            "cwd": str(self.cwd),
            "approvalPolicy": self.approval_policy,
            "sandboxPolicy": self._sandbox_policy(),
        }
        if model:
            turn_params["model"] = model
        if effort:
            turn_params["effort"] = effort
        turn_result = await self.request(
            "turn/start",
            turn_params,
        )
        turn = turn_result.get("turn") or {}
        turn_id = turn.get("id")
        if not turn_id:
            raise CodexProtocolError("App Server did not return a turn id")
        self._active_turn = (active_thread_id, turn_id)
        logger.info("Codex turn started", extra={"thread_id": active_thread_id, "turn_id": turn_id})
        yield {"method": "client/thread", "params": {"threadId": active_thread_id, "turnId": turn_id}}
        try:
            while True:
                message = await self._messages.get()
                params = message.get("params") or {}
                message_turn = params.get("turnId") or (params.get("turn") or {}).get("id")
                message_thread = params.get("threadId") or (params.get("thread") or {}).get("id")
                if message_turn and message_turn != turn_id:
                    continue
                if message_thread and message_thread != active_thread_id:
                    continue
                yield message
                if message.get("method") == "turn/completed":
                    logger.info("Codex turn completed", extra={"thread_id": active_thread_id, "turn_id": turn_id})
                    break
        finally:
            self._active_turn = None

    async def run_command(self, command_text: str) -> dict[str, Any]:
        """Execute a supported Codex slash command through App Server."""
        if not isinstance(command_text, str) or not command_text.strip().startswith("/"):
            raise ValueError("Codex commands must start with '/'")
        parts = shlex.split(command_text.strip())
        name = parts[0].casefold()
        logger.info("Codex slash command requested", extra={"command": name})
        if name == "/models":
            await self.start()
            result = await self.request("model/list", {})
            models = result.get("models", result.get("data", []))
            if not isinstance(models, list):
                models = []
            return {"command": name, "models": models}
        if name == "/status":
            version = await self.check_version()
            result: dict[str, Any] = {
                "command": name,
                "running": self.process is not None and self.process.returncode is None,
                "active_turn": self._active_turn,
                "version": ".".join(map(str, version)),
            }
            if result["running"]:
                result["diagnostics"] = await self.request("server/diagnostics", {})
            return result
        if name == "/help":
            return {
                "command": name,
                "commands": ["/models", "/status", "/help", "/interrupt", "/compact"],
            }
        if name == "/interrupt":
            await self.interrupt()
            return {"command": name, "status": "interrupt requested"}
        if name == "/compact":
            if self._active_turn is None:
                raise CodexProtocolError("/compact requires an active Codex turn")
            thread_id, _turn_id = self._active_turn
            result = await self.request("thread/compact/start", {"threadId": thread_id})
            return {"command": name, **result}
        raise CodexProtocolError(
            f"Unsupported slash command {parts[0]!r} for the App Server adapter"
        )

    async def interrupt(self) -> None:
        if self._active_turn is None:
            return
        thread_id, turn_id = self._active_turn
        await self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
        logger.info("Codex turn interrupt requested", extra={"thread_id": thread_id, "turn_id": turn_id})

    async def respond_to_approval(self, request_id: int, decision: str) -> None:
        """Resolve an approval request previously emitted by the client."""
        future = self._pending_approvals.get(request_id)
        if future is None or future.done():
            raise CodexProtocolError(f"No pending approval request with id {request_id}")
        if not isinstance(decision, str) or not decision.strip():
            raise ValueError("Approval decision must be a non-empty string")
        future.set_result(decision)
        logger.info("Codex approval decision recorded", extra={"request_id": request_id})

    async def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        if process.stdin:
            process.stdin.close()
            await process.stdin.wait_closed()
        try:
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            process.terminate()
            await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader_task, self._stderr_task) if task),
            return_exceptions=True,
        )
        logger.info("Codex App Server client closed")

    async def _ensure_running(self) -> None:
        if self.process is None or self.process.returncode is not None:
            detail = "\n".join(self._stderr[-8:])
            raise CodexProtocolError(f"Codex App Server is not running. {detail}".strip())

    async def _send(self, value: Mapping[str, Any]) -> None:
        await self._ensure_running()
        assert self.process and self.process.stdin
        encoded = (json.dumps(value, separators=(",", ":")) + "\n").encode()
        async with self._write_lock:
            self.process.stdin.write(encoded)
            await self.process.stdin.drain()

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.exception("Codex App Server emitted invalid JSONL")
                    raise CodexProtocolError("App Server emitted invalid JSONL") from exc
                request_id = message.get("id")
                if request_id in self._pending and ("result" in message or "error" in message):
                    future = self._pending[request_id]
                    if not future.done():
                        future.set_result(message)
                elif request_id is not None and "method" in message:
                    await self._handle_server_request(message)
                else:
                    await self._messages.put(message)
            detail = "\n".join(self._stderr[-8:])
            error = CodexProtocolError(f"Codex App Server exited unexpectedly. {detail}".strip())
            logger.error("Codex App Server stdout closed unexpectedly")
        except asyncio.CancelledError:
            return
        except Exception as exc:
            error = exc
            logger.exception("Codex App Server stdout reader failed")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        if "approval" not in method.casefold():
            await self._messages.put(message)
            await self._send({"id": message["id"], "result": {"decision": "cancel"}})
            logger.info("Unsupported server request cancelled", extra={"method": method})
            return

        request_id = message["id"]
        normalized = {
            "method": "client/approval/requested",
            "params": {
                "requestId": request_id,
                "requestMethod": method,
                "request": dict(message.get("params") or {}),
                "approvalPolicy": self.approval_policy,
                "status": "accepted" if self.approval_policy == "never" else "pending",
            },
        }
        if self.approval_policy == "never":
            await self._messages.put(normalized)
            await self._send({"id": request_id, "result": {"decision": "accept"}})
            logger.info("Approval request accepted by policy", extra={"request_id": request_id})
            return

        if self.approval_handler is not None:
            await self._messages.put(normalized)
            decision = await self.approval_handler(normalized)
        else:
            future = asyncio.get_running_loop().create_future()
            self._pending_approvals[request_id] = future
            try:
                await self._messages.put(normalized)
                decision = await future
            finally:
                self._pending_approvals.pop(request_id, None)
        if not isinstance(decision, str) or not decision.strip():
            raise CodexProtocolError("Approval handler returned an invalid decision")
        await self._send({"id": message["id"], "result": {"decision": decision}})
        logger.info("Approval request resolved", extra={"request_id": request_id})

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        try:
            while line := await self.process.stderr.readline():
                self._stderr.append(line.decode("utf-8", errors="replace").rstrip())
                del self._stderr[:-50]
                logger.info("Codex App Server stderr", extra={"stderr": self._stderr[-1]})
        except asyncio.CancelledError:
            return

    def _sandbox_wire_value(self) -> str:
        return {"read-only": "readOnly", "workspace-write": "workspaceWrite", "full-access": "dangerFullAccess"}.get(
            self.sandbox, self.sandbox
        )

    def _sandbox_policy(self) -> dict[str, Any]:
        if self.sandbox == "read-only":
            return {"type": "readOnly"}
        if self.sandbox == "full-access":
            return {"type": "dangerFullAccess"}
        return {
            "type": "workspaceWrite",
            "writableRoots": [str(path) for path in self.writable_roots],
            "networkAccess": self.network_access,
        }
