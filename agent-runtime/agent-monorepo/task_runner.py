"""Run controller-created task messages through the shared agent runtime.

The controller only enqueues `task_request` messages and starts this thin CLI.
This module reads the message, delegates execution to `AgentGateway`, updates
the transparent task record, and sends a reply message to the requester.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

from agents_internal_messaging.bus import MessageBus
from agents_internal_messaging.models import AgentMessage

from .bootstrap import initialize_project
from .events import RuntimeEvent, terminal_event
from .planned_tasks import update_planned_task_status


logger = logging.getLogger(__name__)


async def run_task_message(args: argparse.Namespace) -> int:
    """Execute one queued task message and update messaging task records."""
    project_root = Path(args.project_root).resolve()
    bus = MessageBus(project_root / ".agent-state" / "agents-messaging")
    message_path = Path(args.message_path).resolve()
    message = bus.read(message_path)
    payload = message.payload
    task_id = str(args.task_id or payload.get("task_id") or "")
    agent_id = str(args.agent_id or message.recipient)
    prompt = str(payload.get("prompt") or "").strip()
    plan_id = str(payload.get("plan_id") or "")
    planned_task_id = str(payload.get("planned_task_id") or "")
    if not task_id or not prompt:
        raise ValueError("task runner requires task_id and prompt")

    run_id = str(args.run_id or f"run-{task_id}")
    session_id = str(args.session_id or f"session-{task_id}")
    bus.update_task_status(
        task_id,
        "implementing",
        f"{agent_id} accepted the task.",
        details={"message_id": message.id, "run_id": run_id, "session_id": session_id},
    )
    if plan_id and planned_task_id:
        update_planned_task_status(
            project_root,
            plan_id,
            planned_task_id,
            "implementing",
            f"{agent_id} accepted the task.",
            run_id,
            session_id,
        )
    events: list[RuntimeEvent] = []
    gateway = None
    try:
        gateway = initialize_project(project_root).gateway
        async for event in gateway.run(prompt, run_id=run_id, session_id=session_id, agent_id=agent_id):
            events.append(event)
        finished = terminal_event(events)
        status = "complete" if finished and finished.type == "run.completed" else "need rework"
        final_message = finished.message if finished else "Runtime finished without a terminal event."
        bus.write_task_record(
            {
                "id": task_id,
                "status": status,
                "agent_id": agent_id,
                "message_id": message.id,
                "run_id": run_id,
                "session_id": session_id,
                "plan_id": plan_id,
                "planned_task_id": planned_task_id,
                "summary": final_message or payload.get("title") or task_id,
            }
        )
        bus.update_task_status(
            task_id,
            status,
            final_message or f"Runtime marked task {status}.",
            details={"run_id": run_id, "session_id": session_id, "event_count": len(events)},
        )
        if plan_id and planned_task_id:
            update_planned_task_status(
                project_root,
                plan_id,
                planned_task_id,
                status,
                final_message or f"Runtime marked task {status}.",
                run_id,
                session_id,
            )
        bus.mark_processed(agent_id, message_path)
        bus.send(build_reply(message, agent_id, task_id, status, run_id, session_id, final_message, len(events)))
        return 0 if status == "complete" else 1
    except Exception as exc:
        logger.exception("Controller task runner failed", extra={"task_id": task_id, "agent_id": agent_id})
        bus.update_task_status(
            task_id,
            "need rework",
            f"Task runner failed: {exc}",
            details={"run_id": run_id, "session_id": session_id},
        )
        if plan_id and planned_task_id:
            update_planned_task_status(
                project_root,
                plan_id,
                planned_task_id,
                "need rework",
                f"Task runner failed: {exc}",
                run_id,
                session_id,
            )
        try:
            bus.mark_failed(agent_id, message_path, repr(exc))
        except FileNotFoundError:
            pass
        bus.send(build_reply(message, agent_id, task_id, "need rework", run_id, session_id, str(exc), len(events)))
        return 1
    finally:
        if gateway is not None:
            await gateway.close()


def build_reply(
    message: AgentMessage,
    agent_id: str,
    task_id: str,
    status: str,
    run_id: str,
    session_id: str,
    final_message: str | None,
    event_count: int,
) -> AgentMessage:
    """Build the task result reply message for the original requester."""
    return AgentMessage(
        sender=agent_id,
        recipient=message.sender,
        type="task_request.result",
        payload={
            "ok": status == "complete",
            "task_id": task_id,
            "status": status,
            "run_id": run_id,
            "session_id": session_id,
            "event_count": event_count,
            "message": final_message,
        },
        reply_to=message.id,
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the task runner."""
    parser = argparse.ArgumentParser(description="Run one controller task through the agent runtime")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--message-path", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--session-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one controller task message."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_task_message(args))


if __name__ == "__main__":
    raise SystemExit(main())
