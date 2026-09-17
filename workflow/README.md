# Workflow

Compact workflow resolver and async runner. Declarative workflow YAML lives in
`yamls/`, while `engine.py` owns reference expansion, validation, condition
checks, retry/timeout behavior, bounded parallel groups, and dry-run defaults.

## Commands

```bash
python main.py resolve --workflow analysis
python main.py run --workflow analysis --prompt "inspect"
python test.py
```

Callers can pass handlers to `WorkflowEngine.execute()` for real agent, shell,
tool, message, workflow, controller, or hook behavior.
