from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess

import pytest


def command_starts_codex(command: object) -> bool:
    """Return True when a subprocess command would start native Codex."""
    if isinstance(command, (str, bytes)):
        text = command.decode() if isinstance(command, bytes) else command
        return text.strip().startswith("codex ") or text.strip() == "codex"

    if isinstance(command, (list, tuple)) and command:
        executable = str(command[0])
        return Path(executable).name == "codex"

    return False


@pytest.fixture(autouse=True)
def block_live_model_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent normal tests from launching Codex or using model API keys."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_DISABLE_TEST_MODEL_CALLS", "1")

    original_popen = subprocess.Popen
    original_async_exec = asyncio.create_subprocess_exec
    original_async_shell = asyncio.create_subprocess_shell

    def guarded_popen(command: object, *args: object, **kwargs: object):
        """Block direct native Codex subprocesses in tests."""
        if command_starts_codex(command):
            raise AssertionError("Tests must mock native Codex instead of launching it.")
        return original_popen(command, *args, **kwargs)

    async def guarded_async_exec(program: object, *args: object, **kwargs: object):
        """Block async native Codex subprocesses in tests."""
        command = [program, *args]
        if command_starts_codex(command):
            raise AssertionError("Tests must mock native Codex instead of launching it.")
        return await original_async_exec(program, *args, **kwargs)

    async def guarded_async_shell(command: object, *args: object, **kwargs: object):
        """Block shell-based native Codex subprocesses in tests."""
        if command_starts_codex(command):
            raise AssertionError("Tests must mock native Codex instead of launching it.")
        return await original_async_shell(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", guarded_async_exec)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", guarded_async_shell)
