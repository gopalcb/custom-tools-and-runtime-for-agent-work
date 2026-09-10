# Agents Internal Messaging

This project owns local file-backed Codex agent messaging and the lightweight
hub dispatcher.

Keep messages JSON-serializable and small. Large artifacts should be written to
disk by the handler and referenced by path in reply messages.

