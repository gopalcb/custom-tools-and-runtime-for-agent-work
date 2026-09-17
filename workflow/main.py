"""
CLI facade for the compact workflow engine.

Kept separate so agents can call `python main.py ...` while implementation
details remain in engine.py.
"""

from __future__ import annotations

from engine import main


if __name__ == "__main__":
    raise SystemExit(main())
