"""Read-only Planner Agent CLI.

This module builds a repository-aware prompt, invokes the shared Codex SDK with
a read-only sandbox, validates structured output, and writes planning artifacts.
Application source remains untouched by this workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "agent-runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_monorepo.codex_client import CodexSDKClient
from validation import validate_cli_inputs, validate_plan


AGENT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    """Parse task, repository, output, Codex, and dry-run options."""
    parser = argparse.ArgumentParser(description="Generate a structured implementation plan with Codex CLI.")
    parser.add_argument("task", help="What should be planned")
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--context", default="", help="Additional planning context")
    parser.add_argument("--output-dir", default=".agent-state/plans", help="Planning artifact directory")
    parser.add_argument("--codex-bin", default="", help="Optional native Codex executable")
    parser.add_argument("--model", default="", help="Optional Codex model override")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated prompt without executing Codex")
    return parser.parse_args()


def load_planner_instructions() -> str:
    """Load the permanent planning contract from the registered agent."""
    return (AGENT_DIR / "instructions.md").read_text(encoding="utf-8").strip()


def get_schema_path() -> Path:
    """Return the JSON schema supplied to the Codex SDK."""
    return AGENT_DIR / "plan.schema.json"


def build_prompt(task: str, context: str, repo: Path, planner_instructions: str) -> str:
    """Build a bounded prompt that asks Codex to inspect the repository."""
    context_text = context.strip() or "No additional user context supplied."
    return f"""{planner_instructions}

# Current planning request

## Repository

{repo}

## User task

{task.strip()}

## Additional context

{context_text}

## Required output

Inspect the repository before designing. Reuse existing code where possible.
Return JSON matching the supplied schema with a target tree, component
responsibilities, runtime/data flow, file-level implementation tasks,
dependencies, parallel-safe execution groups, testing, risks, acceptance
criteria, definition of done, and a workflow_id. Do not modify files.
""".strip()


def create_plan(
    prompt: str,
    repo: Path,
    schema_path: Path,
    model: str,
    use_native_codex: bool = False,
) -> dict[str, Any]:
    """Generate one structured plan through the shared SDK client."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    with CodexSDKClient(
        cwd=repo,
        use_native_codex=use_native_codex,
        model=model.strip() or None,
    ) as client:
        plan = client.run_structured(
            prompt,
            schema,
            sandbox="read_only",
            developer_instructions=load_planner_instructions(),
            ephemeral=True,
        )
    validate_plan(plan)
    return plan


def render_plan_markdown(plan: dict[str, Any]) -> str:
    """Render validated structured plan data as readable Markdown."""
    lines = [f"# {plan['title']}", "", plan["summary"], "", f"Execution workflow: `{plan['workflow_id']}`", "", "## Assumptions", ""]
    lines.extend(f"- {item}" for item in plan["assumptions"])
    architecture = plan["architecture"]
    lines.extend(["", "## Target Architecture", "", architecture["overview"], "", "```text", architecture["tree"], "```", "", "## Components", ""])
    for component in architecture["components"]:
        lines.extend([f"### `{component.get('path', 'component')}`", "", str(component.get("purpose", "")), ""])
        lines.extend(f"- {item}" for item in component.get("responsibilities", []))
    lines.extend(["", "## Runtime Flow", ""])
    lines.extend(f"{index}. {step}" for index, step in enumerate(architecture.get("data_flow", []), 1))
    lines.extend(["", "## Implementation Plan", ""])
    for phase in plan["implementation"]["phases"]:
        lines.extend([f"### {phase.get('id', 'Phase')} — {phase.get('name', '')}", "", phase.get("goal", "")])
        for task in phase["tasks"]:
            dependencies = ", ".join(task.get("depends_on", task.get("dependencies", []))) or "none"
            lines.extend(["", f"#### {task['id']} — {task.get('description', '')}", "", f"- Files: {', '.join(task['files'])}", f"- Depends on: {dependencies}", f"- Parallelizable: {task.get('parallelizable', False)}", ""])
            lines.extend(f"- {item}" for item in task.get("details", []))
            lines.append("")
            lines.append("Acceptance criteria:")
            lines.extend(f"- {item}" for item in task.get("acceptance_criteria", []))
    lines.extend(["", "## Testing", ""])
    lines.extend(f"- {item}" for item in plan["testing"])
    lines.extend(["", "## Risks", ""])
    for risk in plan["risks"]:
        if isinstance(risk, dict):
            lines.append(f"- **{risk.get('risk', 'Risk')}** — {risk.get('mitigation', '')}")
        else:
            lines.append(f"- {risk}")
    lines.extend(["", "## Definition of Done", ""])
    lines.extend(f"- {item}" for item in plan["done_criteria"])
    return "\n".join(lines) + "\n"


def create_run_directory(output_base: Path) -> Path:
    """Create a unique UTC directory for one planner execution."""
    stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = output_base / stem
    suffix = 2
    while candidate.exists():
        candidate = output_base / f"{stem}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def main() -> int:
    """Execute the complete read-only planning workflow."""
    args = parse_args()
    repo, output_base, _codex_bin = validate_cli_inputs(
        args.repo, args.output_dir, args.codex_bin, get_schema_path(), args.dry_run
    )
    prompt = build_prompt(args.task, args.context, repo, load_planner_instructions())
    if args.dry_run:
        print(prompt)
        return 0

    run_dir = create_run_directory(output_base)
    plan_path = run_dir / "plan.json"
    plan = create_plan(prompt, repo, get_schema_path(), args.model, bool(args.codex_bin.strip()))
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (run_dir / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    (run_dir / "PLAN.md").write_text(render_plan_markdown(plan), encoding="utf-8")
    print(f"Plan created: {run_dir / 'PLAN.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
