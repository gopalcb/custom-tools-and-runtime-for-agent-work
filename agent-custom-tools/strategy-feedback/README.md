# Strategy Feedback

Compact post-work feedback collection and analysis.

## Commands

```bash
python main.py collect --run-id run-1 --session-id session-1 --prompt "Do work"
python main.py analyze --feedback-file feedback.json
python test.py
```

`feedback_coordinator.py` supports fixture-driven collection through
`AGENT_STRATEGY_FEEDBACK_RESPONSE`, a Tkinter GUI fallback, JSON analysis
parsing, and conservative local memory/rework classification.
