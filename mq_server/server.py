"""
Exposes a compact FastAPI MQ control plane.

The server accepts message events, persists each state transition, processes the
queue in a background worker, and exposes health plus message inspection routes.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from handler import process_event
from store import LocalStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MESSAGE_STORE: dict[str, dict[str, dict]] = {}
EVENT_QUEUE: asyncio.Queue[dict] = asyncio.Queue()
ACTIVE_TASKS: set[asyncio.Task] = set()


class MessageRequest(BaseModel):
    """Validated request body for one MQ message."""

    topic: str = Field(min_length=1)
    sender: str = "unknown"
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: str | None = None


def timestamp_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def build_event(request: MessageRequest) -> dict:
    """Build the in-memory event representation."""
    return {
        "event_id": request.event_id or f"evt_{uuid4().hex}",
        "topic": request.topic,
        "status": "pending",
        "sender": request.sender,
        "payload": request.payload,
        "timestamp": timestamp_now(),
        "result": None,
    }


def remember_event(event: dict) -> None:
    """Store the latest event state in memory."""
    MESSAGE_STORE.setdefault(event["topic"], {})[event["event_id"]] = dict(event)


def persist_event(event: dict) -> None:
    """Persist the latest event state to disk."""
    LocalStore(PROJECT_ROOT).save_event(event["topic"], event)


async def worker_loop() -> None:
    """Process queued events until cancelled."""
    while True:
        event = await EVENT_QUEUE.get()
        try:
            event["status"] = "processing"
            remember_event(event)
            persist_event(event)
            event["result"] = process_event(PROJECT_ROOT, event)
            event["status"] = "processed"
            remember_event(event)
            persist_event(event)
        except Exception as error:
            event["result"] = {"ok": False, "error": str(error), "error_type": type(error).__name__}
            event["status"] = "processed"
            remember_event(event)
            persist_event(event)
        finally:
            EVENT_QUEUE.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the background worker."""
    task = asyncio.create_task(worker_loop())
    ACTIVE_TASKS.add(task)
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        ACTIVE_TASKS.discard(task)


app = FastAPI(title="Compact Local Agent MQ", version="1", lifespan=lifespan)


@app.post("/messages")
async def post_message(request: MessageRequest) -> dict:
    """Accept a message event, persist it, and enqueue processing."""
    event = build_event(request)
    remember_event(event)
    persist_event(event)
    await EVENT_QUEUE.put(event)
    return {"event_id": event["event_id"], "status": event["status"]}


@app.get("/messages/{event_id}")
async def get_message(event_id: str) -> dict:
    """Return the latest in-memory state for one event."""
    for topic_events in MESSAGE_STORE.values():
        if event_id in topic_events:
            return topic_events[event_id]
    raise HTTPException(status_code=404, detail="message not found")


@app.get("/messages")
async def list_messages() -> dict:
    """Return all in-memory message events grouped by topic."""
    return MESSAGE_STORE


@app.get("/health")
async def health() -> dict:
    """Report MQ liveness and queue depth."""
    return {"status": "healthy", "alive": True, "ready": True, "queued": EVENT_QUEUE.qsize(), "active_tasks": len(ACTIVE_TASKS)}
