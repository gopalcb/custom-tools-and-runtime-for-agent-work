"""Local messaging primitives for Codex agents."""

from .bus import MessageBus
from .models import AgentMessage, MessageRecord

__all__ = ["AgentMessage", "MessageBus", "MessageRecord"]
