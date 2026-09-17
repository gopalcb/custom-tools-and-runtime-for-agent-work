"""
Single CLI entry point for compact knowledge-search tools.

Subcommands route to web_search.py, research.py, and log_search.py while keeping
each behavior in its own direct file.
"""

from __future__ import annotations

import argparse

import log_search
import research
import web_search


def main(argv: list[str] | None = None) -> int:
    """Dispatch a knowledge-search subcommand."""
    parser = argparse.ArgumentParser(description="Compact knowledge-search tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("web", add_help=False)
    sub.add_parser("research", add_help=False)
    sub.add_parser("logs", add_help=False)
    args, rest = parser.parse_known_args(argv)
    if args.command == "web":
        return web_search.main(rest)
    if args.command == "research":
        return research.main(rest)
    return log_search.main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
