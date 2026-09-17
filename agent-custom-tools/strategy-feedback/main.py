"""
JSON CLI for compact strategy feedback.

Use `collect` for the GUI/fixture flow and `analyze` for fallback analyzer
behavior over an existing JSON feedback payload.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from feedback_coordinator import StrategyFeedbackCoordinator, fallback_analysis, load_feedback_response


def main(argv: list[str] | None = None) -> int:
    """Run a compact strategy-feedback command."""
    parser = argparse.ArgumentParser(description="Compact strategy feedback")
    parser.add_argument("--project-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--session-id", required=True)
    collect.add_argument("--prompt", default="")
    collect.add_argument("--agent-id", default="compact-agent")
    collect.add_argument("--output")
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--feedback-file", required=True)
    args = parser.parse_args(argv)
    coordinator = StrategyFeedbackCoordinator(args.project_root)
    if args.command == "collect":
        context = {
            "run_id": args.run_id,
            "session_id": args.session_id,
            "prompt": args.prompt,
            "agent_id": args.agent_id,
            "output": args.output,
        }
        result = asyncio.run(coordinator.collect_feedback(context))
    else:
        result = fallback_analysis(load_feedback_response(Path(args.feedback_file)))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") != "unavailable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
