"""
Builds compact research notes from one or more web-search questions.

The file is intentionally small: it composes web_search.py, adds a topic-level
summary envelope, and persists Markdown for easy agent handoff.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from web_search import SearchRequest, json_to_markdown, search


def run_research(topic: str, questions: list[str], cwd: str | Path = ".", model: str | None = None) -> dict:
    """Run several searches and return one research bundle."""
    if not topic.strip():
        raise ValueError("topic must be non-empty")
    if not questions:
        questions = [topic]
    results = [search(SearchRequest(query=question, cwd=cwd, model=model)) for question in questions]
    return {"topic": topic, "questions": questions, "results": results}


def research_to_markdown(bundle: dict) -> str:
    """Render a research bundle as Markdown."""
    sections = [f"# Research: {bundle['topic']}\n"]
    for index, result in enumerate(bundle["results"], start=1):
        sections.append(f"\n## Finding {index}\n")
        sections.append(json_to_markdown(result))
    return "\n".join(sections)


def save_research(bundle: dict, output_directory: str | Path = "output") -> Path:
    """Save a research bundle as Markdown and JSON."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    stem = "".join(character if character.isalnum() else "-" for character in str(bundle["topic"]).lower()).strip("-")[:80] or "research"
    markdown_path = output / f"{stem}.md"
    json_path = output / f"{stem}.json"
    markdown_path.write_text(research_to_markdown(bundle), encoding="utf-8")
    json_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return markdown_path


def main(argv: list[str] | None = None) -> int:
    """Run compact research from the command line."""
    parser = argparse.ArgumentParser(description="Run compact multi-question research")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--model")
    parser.add_argument("--output-directory", default="output")
    args = parser.parse_args(argv)
    bundle = run_research(args.topic, args.question, args.cwd, args.model)
    path = save_research(bundle, args.output_directory)
    print(json.dumps({"path": str(path), "bundle": bundle}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
