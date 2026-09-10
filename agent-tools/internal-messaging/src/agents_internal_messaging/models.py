"""Data contracts for durable messages and their lifecycle records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AgentMessage:
    sender: str
    recipient: str
    type: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=utc_now_iso)
    reply_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.type,
            "payload": self.payload,
        }
        if self.reply_to:
            data["reply_to"] = self.reply_to
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        return cls(
            id=str(data["id"]),
            created_at=str(data["created_at"]),
            sender=str(data["sender"]),
            recipient=str(data["recipient"]),
            type=str(data["type"]),
            payload=dict(data.get("payload") or {}),
            reply_to=str(data["reply_to"]) if data.get("reply_to") else None,
        )


@dataclass(frozen=True)
class MessageRecord:
    message: AgentMessage
    status: str
    path: str
    folder_agent_id: str
    updated_at: str = field(default_factory=utc_now_iso)
    error: str | None = None

    def to_dict(self, *, include_payload: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.message.id,
            "created_at": self.message.created_at,
            "updated_at": self.updated_at,
            "sender": self.message.sender,
            "recipient": self.message.recipient,
            "type": self.message.type,
            "reply_to": self.message.reply_to,
            "status": self.status,
            "path": self.path,
            "folder_agent_id": self.folder_agent_id,
        }
        if include_payload:
            data["payload"] = self.message.payload
        if self.error:
            data["error"] = self.error
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MessageRecord":
        return cls(
            message=AgentMessage(
                id=str(data["id"]),
                created_at=str(data["created_at"]),
                sender=str(data["sender"]),
                recipient=str(data["recipient"]),
                type=str(data["type"]),
                payload=dict(data.get("payload") or {}),
                reply_to=str(data["reply_to"]) if data.get("reply_to") else None,
            ),
            status=str(data["status"]),
            path=str(data["path"]),
            folder_agent_id=str(data["folder_agent_id"]),
            updated_at=str(data.get("updated_at") or data["created_at"]),
            error=str(data["error"]) if data.get("error") else None,
        )
