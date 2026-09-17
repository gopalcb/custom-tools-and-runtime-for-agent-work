# Knowledge Search

Compact knowledge tooling split into three direct files:

- `web_search.py`: structured Codex-backed web research.
- `research.py`: multi-question research bundles.
- `log_search.py`: local log search and error-object recording.

## Commands

```bash
python main.py web --query "What changed?"
python main.py research --topic "Agent runtime" --question "What is the source of truth?"
python main.py logs find --root .agent-state/logs --query ERROR
python test.py
```

The web path imports the shared Codex SDK lazily, so local tests avoid live
network or model calls.
