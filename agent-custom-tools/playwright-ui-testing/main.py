"""
CLI entry points for the compact Playwright UI testing tool.

The commands expose browser startup, screenshot capture, network tracing,
console-error capture, and DOM hydration checks as small JSON-producing calls.
"""

from __future__ import annotations

import argparse
import json

from chrome_browser import check_page_open, get_page, open_chrome
from operations import capture_page_screenshot, get_console_errors, trace_network_calls, validate_dom_hydration


def build_parser() -> argparse.ArgumentParser:
    """Create the Playwright tool parser."""
    parser = argparse.ArgumentParser(description="Compact Playwright UI testing tool")
    sub = parser.add_subparsers(dest="command", required=True)
    open_parser = sub.add_parser("open")
    open_parser.add_argument("--url")
    open_parser.add_argument("--headless", action="store_true")
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--url")
    screenshot = sub.add_parser("screenshot")
    screenshot.add_argument("--url")
    screenshot.add_argument("--output", default=".agent-state/playwright-ui-testing/screenshot.png")
    screenshot.add_argument("--viewport-only", action="store_true")
    network = sub.add_parser("network")
    network.add_argument("--url")
    network.add_argument("--duration-ms", type=int, default=1500)
    network.add_argument("--reload", action="store_true")
    console = sub.add_parser("console-errors")
    console.add_argument("--url")
    console.add_argument("--duration-ms", type=int, default=1000)
    console.add_argument("--reload", action="store_true")
    hydration = sub.add_parser("hydration")
    hydration.add_argument("--url")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one Playwright tool command and print JSON."""
    args = build_parser().parse_args(argv)
    if args.command == "open":
        result = open_chrome(headless=args.headless)
        if args.url:
            page = get_page(args.url, headless=args.headless)
            result["url"] = page.url
    elif args.command == "check":
        result = check_page_open(args.url)
    elif args.command == "screenshot":
        result = capture_page_screenshot(args.url, args.output, not args.viewport_only)
    elif args.command == "network":
        result = trace_network_calls(args.url, args.duration_ms, args.reload)
    elif args.command == "console-errors":
        result = get_console_errors(args.url, args.duration_ms, args.reload)
    else:
        result = validate_dom_hydration(args.url)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
