# Event Messaging

Direct-folder file-backed messaging for local agents. It keeps inbox,
processed, failed, record, task, event, and current-error state under one root.

## Commands

```bash
python main.py --root /tmp/messages send --sender tester --recipient agent-health --type health.request
python main.py --root /tmp/messages list
python main.py --root /tmp/messages hub run-once
python test.py
```

This folder intentionally does not contain a nested package directory or
`AGENTS.md`.
