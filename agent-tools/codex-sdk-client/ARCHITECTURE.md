# Codex SDK Client API

This local Flask API exposes the shared `CodexSDKClient` without reproducing
the Codex App Server protocol. Text and structured routes use synchronous SDK
turns; turn routes expose SDK streaming, steering, and interruption handles.

`GET /v1/turns/<turn_id>/stream` returns newline-delimited JSON. Each line is
the SDK notification serialized as JSON, preserving the agent/tool/file-change
activity a Codex CLI client receives. The API owns only process-local active
handles; a reconnecting client must retain its turn id and use a still-running
service process.
