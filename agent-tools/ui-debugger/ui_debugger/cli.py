"""Command-line entry point for running one Selenium UI debug request."""

from __future__ import annotations

import argparse
import json

from .runner import DebugRequest, run_debug_request


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, run the debugger, and print JSON output."""
    parser = argparse.ArgumentParser(description="Run one Selenium UI debug request")
    parser.add_argument("url")
    parser.add_argument("--request-id")
    parser.add_argument("--requester")
    parser.add_argument("--artifact-root")
    parser.add_argument("--wait-seconds", type=float, default=1.0)
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1000)
    parser.add_argument("--viewport-only", action="store_true")
    args = parser.parse_args(argv)

    request = DebugRequest.from_dict(
        {
            "url": args.url,
            "request_id": args.request_id,
            "requester": args.requester,
            "artifact_root": args.artifact_root,
            "wait_seconds": args.wait_seconds,
            "viewport_width": args.viewport_width,
            "viewport_height": args.viewport_height,
            "full_page_screenshot": not args.viewport_only,
        }
    )
    result = run_debug_request(request)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
