# Memory Server

Compact JSON memory storage and lexical search. Records are written under
`.agent-state/cache/memory/records/`.

## Commands

The module is usually called through `runtime.py` or `mq_server/handler.py`.

```bash
python test.py
```

Stored memories require task, summary, and validation text. Secret-looking
assignments are rejected before persistence.
