"""Open a small Tkinter form for post-work feedback.

The script writes one JSON response file for the runtime. It has no dependency
on the runtime package so it can fail cleanly in headless desktop sessions.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def utc_now() -> str:
    """Return the current UTC time in ISO 8601 form."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_response(path: Path, payload: dict) -> None:
    """Persist the submitted feedback response."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the feedback form."""
    parser = argparse.ArgumentParser(description="Collect strategy-memory feedback.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", required=True)
    return parser


def run_form(args: argparse.Namespace) -> None:
    """Display the feedback form and write submit/cancel state."""
    output = Path(args.output)
    root = tk.Tk()
    root.title("Codex work feedback")
    root.geometry("560x460")
    root.minsize(480, 380)

    store_memory = tk.BooleanVar(value=True)
    feedback_label = tk.Label(root, text="Feedback about this work")
    feedback_label.pack(anchor="w", padx=14, pady=(14, 4))
    feedback_text = tk.Text(root, height=9, wrap="word")
    feedback_text.pack(fill="both", expand=True, padx=14)

    change_label = tk.Label(root, text="Anything to fix or do differently")
    change_label.pack(anchor="w", padx=14, pady=(12, 4))
    change_text = tk.Text(root, height=5, wrap="word")
    change_text.pack(fill="both", expand=True, padx=14)

    checkbox = tk.Checkbutton(root, text="Store this work memory", variable=store_memory)
    checkbox.pack(anchor="w", padx=12, pady=10)

    buttons = tk.Frame(root)
    buttons.pack(fill="x", padx=14, pady=(0, 14))

    def submit() -> None:
        """Write a submitted feedback response and close the form."""
        payload = {
            "status": "submitted",
            "store_work_memory": bool(store_memory.get()),
            "feedback": feedback_text.get("1.0", "end").strip(),
            "requested_change": change_text.get("1.0", "end").strip(),
            "run_id": args.run_id,
            "session_id": args.session_id,
            "submitted_at": utc_now(),
        }
        write_response(output, payload)
        root.destroy()

    def cancel() -> None:
        """Write a cancelled response and close the form."""
        write_response(
            output,
            {
                "status": "cancelled",
                "run_id": args.run_id,
                "session_id": args.session_id,
                "submitted_at": utc_now(),
            },
        )
        root.destroy()

    submit_button = tk.Button(buttons, text="Submit", command=submit)
    submit_button.pack(side="right", padx=(8, 0))
    cancel_button = tk.Button(buttons, text="Cancel", command=cancel)
    cancel_button.pack(side="right")
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()


def main() -> int:
    """Run the feedback form and report headless failures as JSON."""
    args = build_parser().parse_args()
    try:
        run_form(args)
    except tk.TclError as exc:
        write_response(
            Path(args.output),
            {
                "status": "unavailable",
                "reason": str(exc),
                "run_id": args.run_id,
                "session_id": args.session_id,
                "submitted_at": utc_now(),
            },
        )
        return 2
    except OSError as exc:
        messagebox.showerror("Codex work feedback", str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
