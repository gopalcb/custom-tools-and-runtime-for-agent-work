# Interactive Web Search Architecture

`cli.py` is the only active entry point. It loads `search-config.yaml`,
validates a prompt and profile before starting Selenium, then delegates browser
actions to `services/browser.py` and response polling/storage to
`services/extractor.py`.

The active `chatgpt` profile uses Chrome's existing local profile so its
already-authenticated session can be reused. Browser profile data is never
copied, exported, or written by this tool. `google` is registered but disabled
until it has profile-specific extraction behavior.

Responses are considered complete when the newest assistant message appears
after prompt submission and its text remains unchanged for the configured
stability window. Only the extracted text is saved, in timestamped files under
`output/`, which is created on demand.

`api.py` is a small local proxy for `agent-tools/codex-sdk-client/api.py`. It
calls the client health, turn, stream, steer, and interrupt endpoints and
passes raw NDJSON Codex event logs through unchanged. The Nest controller uses
this stable debugger boundary instead of reaching into the SDK process.
