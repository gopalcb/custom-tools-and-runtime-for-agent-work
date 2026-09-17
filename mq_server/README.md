# MQ Server

Compact FastAPI message queue plus deterministic handler.

## Commands

```bash
uvicorn server:app --host 127.0.0.1 --port 8010
python test.py
```

Supported handler topics include `todo`, `read-file`, `write-file`,
`update-file`, `delete-file`, `run-workflow`, `memory-store`, `memory-search`,
`memory-health`, generic `memory`, `invoke-function`, and `system-error`.
