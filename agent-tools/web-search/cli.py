"""Run one structured, Codex-backed web search from the command line."""

import argparse
import json

from model import SearchRequest
from service import DEFAULT_SEARCH_INSTRUCTIONS, save_markdown, search


def parse_args() -> argparse.Namespace:
    """Parse one Codex-backed research request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", "--prompt", dest="query", required=True, help="Question to research.")
    parser.add_argument("--instructions", default=DEFAULT_SEARCH_INSTRUCTIONS)
    parser.add_argument("--cwd", default=".", help="Codex working directory.")
    parser.add_argument("--model")
    parser.add_argument("--output-directory", default="output")
    return parser.parse_args()


def main() -> None:
    """Run one search, save the Markdown rendering, and print JSON output."""
    args = parse_args()
    response = search(
        SearchRequest(
            query=args.query,
            instructions=args.instructions,
            cwd=args.cwd,
            model=args.model,
        )
    )
    markdown_path = save_markdown(response, args.output_directory)
    print(json.dumps({"response": response, "markdown_path": str(markdown_path)}, indent=2))


if __name__ == "__main__":
    main()
