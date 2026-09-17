"""
Compact custom-agent runtime facade.

This file ties together the simplified workflow engine, MQ handler, memory
server, event messaging, and strategy feedback tool without reproducing the
full monorepo runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from runtime_support import RunContext


LIB_ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    """Load one compact library module by path."""
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


class CompactAgentRuntime:
    """Small orchestration facade for compact local agent tools."""

    def __init__(self, project_root: str | Path = ".") -> None:
        """Create a compact runtime rooted at a project."""
        self.project_root = Path(project_root).resolve()
        self.memory = load_module("compact_runtime_memory", LIB_ROOT / "memory-server" / "server.py")
        self.workflow = load_module("compact_runtime_workflow", LIB_ROOT / "workflow" / "engine.py")
        self.mq_handler = load_module("compact_runtime_mq_handler", LIB_ROOT / "mq_server" / "handler.py")
        messaging_dir = LIB_ROOT / "agent-custom-tools" / "event-messaging"
        if str(messaging_dir) not in sys.path:
            sys.path.insert(0, str(messaging_dir))
        from bus import MessageBus

        self.message_bus = MessageBus(self.project_root / ".agent-state" / "agents-messaging")

    def create_context(self, prompt: str, workflow_id: str = "analysis", agent_id: str = "compact-agent") -> RunContext:
        """Create a run context with deterministic compact IDs."""
        safe = "".join(character if character.isalnum() else "-" for character in workflow_id).strip("-") or "workflow"
        return RunContext(
            project_root=self.project_root,
            run_id=f"run-{safe}",
            session_id=f"session-{safe}",
            agent_id=agent_id,
            prompt=prompt,
            workflow_id=workflow_id,
        )

    def resolve_workflow(self, workflow_id: str = "analysis") -> dict:
        """Resolve a workflow from compact YAMLs."""
        return self.workflow.resolve_workflow_request(self.project_root, {"workflow": workflow_id})

    async def run_workflow(self, prompt: str, workflow_id: str = "analysis", agent_id: str = "compact-agent") -> dict:
        """Dry-run a compact workflow and emit runtime events."""
        context = self.create_context(prompt, workflow_id, agent_id)
        context.emit("runtime.started", "running", "Compact runtime started", {"workflow_id": workflow_id})
        result = await self.workflow.run_workflow(workflow_id, prompt, agent_id)
        context.data["workflow"] = result
        context.emit("runtime.completed", result["status"], "Compact runtime completed", {"workflow_id": workflow_id})
        return {"context": context_summary(context), "workflow": result}

    def process_message(self, topic: str, payload: dict, sender: str = "compact-agent") -> dict:
        """Process one MQ-style message synchronously through the compact handler."""
        event = {
            "event_id": f"evt-{topic}",
            "topic": topic,
            "sender": sender,
            "payload": payload,
            "timestamp": "",
        }
        return self.mq_handler.process_event(self.project_root, event)

    def remember(self, original_task: str, summary: str, validation: str, files: list[str] | None = None) -> dict:
        """Store one compact memory record."""
        return self.memory.store_memory(
            self.project_root,
            {
                "original_task": original_task,
                "summary": summary,
                "validation": validation,
                "files": files or [],
            },
            {"topic": "runtime.remember", "sender": "compact-agent"},
        )

    def search_memory(self, query: str, limit: int = 5) -> dict:
        """Search compact memory records."""
        return self.memory.search_memory(self.project_root, {"query": query, "limit": limit})

    def send_agent_message(self, sender: str, recipient: str, message_type: str, payload: dict) -> str:
        """Send one durable agent message and return its path."""
        from models import AgentMessage

        path = self.message_bus.send(AgentMessage(sender, recipient, message_type, payload))
        return str(path)


def context_summary(context: RunContext) -> dict:
    """Return a JSON-compatible summary of a run context."""
    return {
        "project_root": str(context.project_root),
        "run_id": context.run_id,
        "session_id": context.session_id,
        "agent_id": context.agent_id,
        "workflow_id": context.workflow_id,
        "events": [event.to_dict() for event in context.events],
        "data": context.data,
    }


def main(argv: list[str] | None = None) -> int:
    """Run compact runtime commands from the terminal."""
    parser = argparse.ArgumentParser(description="Compact custom-agent runtime")
    parser.add_argument("--project-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    resolve = sub.add_parser("resolve-workflow")
    resolve.add_argument("--workflow", default="analysis")
    run = sub.add_parser("run")
    run.add_argument("--workflow", default="analysis")
    run.add_argument("--prompt", required=True)
    remember = sub.add_parser("remember")
    remember.add_argument("--task", required=True)
    remember.add_argument("--summary", required=True)
    remember.add_argument("--validation", required=True)
    remember.add_argument("--file", action="append", default=[])
    search = sub.add_parser("search-memory")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    runtime = CompactAgentRuntime(args.project_root)
    if args.command == "resolve-workflow":
        result = runtime.resolve_workflow(args.workflow)
    elif args.command == "run":
        result = asyncio.run(runtime.run_workflow(args.prompt, args.workflow))
    elif args.command == "remember":
        result = runtime.remember(args.task, args.summary, args.validation, args.file)
    else:
        result = runtime.search_memory(args.query, args.limit)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
