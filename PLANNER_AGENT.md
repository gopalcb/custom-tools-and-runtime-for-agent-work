# Planner Agent — Complete Design, Architecture, Code Map, Prompt Contract, and Implementation Plan

## 1. Purpose

The **Planner Agent** is a repository-aware planning agent that converts a user request into a detailed, implementation-ready software plan.

Its primary responsibilities are:

- accept a user task;
- inspect the existing repository before proposing changes;
- understand current architecture, reusable code, existing agents, services, utilities, schemas, and conventions;
- create a compact tree-based target architecture;
- identify which existing files should be reused or modified;
- identify new files only when necessary;
- generate detailed implementation phases and tasks;
- map dependencies between tasks;
- identify tasks that can safely run in parallel;
- include testing, validation, risks, and completion criteria;
- keep architecture documentation and `code-map.yaml` changes in the plan when source ownership changes;
- remain a **planning-only** agent and not modify application source code.

The Planner Agent uses **Python to call Codex CLI** and requires Codex to return a structured result.

---

# 2. High-Level Architecture

```text
monorepo/
│
├── agents/
│   ├── planner-agent/
│   │   └── PLANNER_AGENT.md
│   │
│   ├── agent-builder/
│   ├── agent-ui-builder/
│   └── ...
│
├── agent-runtime/
│   └── agent-monorepo/
│       ├── resolver.py
│       ├── semantic_search.py
│       └── bootstrap.py
│
├── workflow-orchestrator/
│   └── ...
│
├── ARCHITECTURE.md
├── code-map.yaml
├── project-registry.yaml
│
└── .agent-state/
    ├── plans/
    │   └── <UTC-run-id>/
    │       ├── prompt.md
    │       ├── plan.json
    │       └── PLAN.md
    │
    ├── sessions/
    ├── logs/
    └── cache/
```

`PLANNER_AGENT.md` is the single specification file for the Planner Agent.

It contains:

- architecture;
- agent behavior;
- runtime flow;
- prompt design;
- output schema;
- Python implementation blueprint;
- validation approach;
- `code-map.yaml` definition;
- implementation phases;
- testing strategy;
- integration contract;
- future extensions.

---

# 3. Planner Agent Position in the Agent System

```text
User
  │
  ▼
Agent Gateway / CLI
  │
  ▼
Agent Resolver
  │
  ├── resolve agent
  ├── resolve skills
  ├── resolve repository context
  └── resolve workflow
  │
  ▼
Planner Agent
  │
  ├── inspect repository
  ├── inspect architecture
  ├── inspect code map
  ├── identify reusable code
  ├── design target architecture
  └── generate structured implementation plan
  │
  ▼
Workflow Orchestrator
  │
  ├── resolve dependencies
  ├── create execution groups
  ├── assign worker agents
  └── run parallel work where safe
  │
  ▼
Worker Agents
  │
  ▼
Validator / Observer
```

The Planner Agent answers:

> **What should be built, where should it be built, what should be reused, and in what order should implementation happen?**

The Workflow Orchestrator answers:

> **Which agent should execute each task, and when?**

Worker agents answer:

> **How do I implement my assigned task?**

---

# 4. Design Principles

## 4.1 Inspect Before Designing

The Planner Agent must inspect the repository before proposing architecture.

It should look for:

```text
ARCHITECTURE.md
code-map.yaml
project-registry.yaml
AGENT_MAP.md
agent.yaml
README.md
pyproject.toml
package.json
requirements.txt
existing source modules
existing services
existing validators
existing agents
existing schemas
existing tests
```

The Planner Agent must not assume that a new service or module is required before searching for an existing reusable implementation.

---

## 4.2 Prefer Reuse

Before creating a new file, the planner should ask:

1. Does a similar module already exist?
2. Can an existing function be extended?
3. Is there already a shared validator?
4. Is there already an orchestration utility?
5. Is there already a schema that can be extended?
6. Is the proposed abstraction actually needed?

The plan should explicitly mention reusable code.

Example:

```text
Reuse:
- agent-runtime/agent-monorepo/resolver.py
- packages/common/validation.py

Modify:
- resolver.py → add planner-agent resolution

Create:
- planner execution adapter only if no equivalent exists
```

---

# 5. Avoid Over-Engineering

The planner should prefer compact architecture.

Avoid structures like:

```text
planner/
├── planner_manager.py
├── planner_factory.py
├── planner_service.py
├── prompt_builder.py
├── prompt_manager.py
├── output_manager.py
├── plan_formatter.py
├── command_runner.py
├── codex_manager.py
├── codex_factory.py
└── ...
```

unless the repository genuinely requires those abstractions.

Prefer:

```text
planner-agent/
├── planner.py
├── validation.py
└── planner instructions/config
```

For your broader monorepo, the planner should continue following the principle:

> Create a new file only when that file has a clear, independent responsibility.

---

# 6. Function Design Guidelines

For Python projects:

- functions should not be extremely large;
- functions should also not be split into unnecessary one-line or two-line wrappers;
- function names should make the execution flow obvious;
- imports must stay at the top of the file;
- validation should be centralized instead of mixed into business logic;
- module-level docstrings should briefly explain the file;
- function docstrings should briefly explain each function;
- architecture files and code maps should stay synchronized with structural changes.

Example preferred flow:

```text
main()
 ├── parse_args()
 ├── validate_cli_inputs()
 ├── build_prompt()
 ├── run_codex()
 ├── validate_plan()
 └── render_plan_markdown()
```

This is easier for humans and agents to follow than many nested abstractions.

---

# 7. Runtime Flow

```text
User task
   │
   ▼
planner.py
   │
   ├── validate repository
   ├── validate Codex CLI
   ├── load planning instructions
   ├── build structured prompt
   │
   ▼
Codex CLI
   │
   │ read-only repository inspection
   │
   ▼
Structured plan JSON
   │
   ├── validate required sections
   ├── validate task IDs
   ├── validate architecture tree
   │
   ▼
PLAN.md
```

---

# 8. Codex CLI Invocation

The Planner Agent should use the headless Codex CLI.

Conceptually:

```bash
codex exec \
  --sandbox read-only \
  --output-schema schemas/plan.schema.json \
  --output-last-message .agent-state/plans/<run-id>/plan.json \
  -
```

The `-` means the planning prompt is passed through stdin.

Python should use:

```python
subprocess.run(
    command,
    input=prompt,
    text=True,
    cwd=repo,
    capture_output=True,
)
```

This avoids shell escaping problems for large prompts.

---

# 9. Planner CLI Contract

Recommended CLI:

```bash
python planner.py \
  "Build a UI debugger agent using Selenium" \
  --repo /path/to/monorepo \
  --context "Keep the architecture compact."
```

Optional flags:

```text
task              required planning request

--repo            target repository
--context         optional additional constraints
--output-dir      plan output location
--codex-bin       Codex executable
--model           optional model override
--dry-run         print prompt without invoking Codex
```

---

# 10. Planner Agent Configuration Contract

Equivalent conceptual `agent.yaml` configuration:

```yaml
name: planner-agent
version: 1

purpose: >
  Inspect an existing repository and convert a user request into a structured,
  tree-first implementation plan for downstream coding agents.

runtime:
  language: python
  entrypoint: planner.py
  engine: codex-cli
  codex_command: codex exec
  repository_access: read-only

inputs:
  required:
    - task

  optional:
    - repo
    - context
    - output_dir
    - model

outputs:
  base_path: .agent-state/plans

  artifacts:
    - prompt.md
    - plan.json
    - PLAN.md

planning_rules:
  inspect_repository_first: true
  modify_source_files: false
  prefer_code_reuse: true
  prefer_compact_architecture: true
  include_tree_architecture: true
  include_task_dependencies: true
  identify_parallel_work: true
  update_architecture_docs_in_plan_when_needed: true
```

---

# 11. Core Planner Instructions

The following should be treated as the Planner Agent's permanent instruction set.

```text
You are a senior software architect and implementation planner operating
inside an existing repository.

Your job is to convert a user request into a precise implementation plan.

You inspect first, design second, and never modify application source files.

Repository-aware behavior:

- Inspect the repository before designing.
- Read ARCHITECTURE.md when present.
- Read code-map.yaml when present.
- Read AGENT_MAP.md and project-registry.yaml when present.
- Inspect source files directly related to the requested change.
- Search for reusable functions and services before proposing new ones.
- Follow existing naming and architectural conventions.

Architecture behavior:

- Keep architecture compact.
- Avoid unnecessary abstractions.
- Avoid unnecessary files.
- Avoid unnecessary managers, factories, services, wrappers, and adapters.
- Prefer cohesive modules and reusable functions.
- Every new file must have a concrete responsibility.

Plan format:

- Start with a repository-aware summary.
- Include assumptions.
- Include a target tree architecture.
- Include component responsibilities.
- Include runtime/data flow.
- Include detailed implementation phases.
- Every implementation task must identify affected files.
- Every task must identify dependencies.
- Mark tasks that can safely execute in parallel.
- Include acceptance criteria.
- Include testing and validation steps.
- Include risks and mitigations.
- Include definition of done.

Architecture synchronization:

- If Python source structure changes, include required ARCHITECTURE.md updates.
- If functions/files change, include required code-map.yaml updates.
- Avoid duplicating documentation across many files.

Safety:

- Planning only.
- Do not edit application source.
- Do not install dependencies.
- Do not deploy infrastructure.
- Do not execute destructive operations.
```

---

# 12. Structured Prompt Template

The Python wrapper should construct the final prompt approximately like this:

```text
<permanent planner instructions>

# Current planning request

## Repository

{repo_path}

## User task

{task}

## Additional context

{context}

## Required planning behavior

- Inspect the repository before deciding architecture.
- Reuse existing modules and functions where reasonable.
- Read ARCHITECTURE.md and code-map.yaml when available.
- Keep architecture compact.
- Do not generate unnecessary files.
- Produce a target tree.
- Produce component responsibilities.
- Produce implementation phases.
- Include file-level changes.
- Include dependencies.
- Identify parallelizable tasks.
- Include validation/testing.
- Include risks.
- Include definition of done.
- Planning only.
- Return JSON matching the required output schema.
```

---

# 13. Structured Planner Output

The Planner Agent should return machine-readable structured JSON.

Recommended structure:

```json
{
  "title": "Planner Agent Implementation",
  "summary": "Short repository-aware summary.",
  "assumptions": [
    "Assumption 1"
  ],
  "architecture": {
    "overview": "Architecture explanation.",
    "tree": "tree representation",
    "components": [
      {
        "path": "agents/planner-agent/planner.py",
        "purpose": "Planner orchestration",
        "responsibilities": [
          "Build prompt",
          "Invoke Codex"
        ],
        "depends_on": []
      }
    ],
    "data_flow": [
      "User request enters planner.",
      "Planner builds Codex prompt.",
      "Codex inspects repository.",
      "Structured plan is generated."
    ]
  },
  "implementation": {
    "phases": [
      {
        "id": "P1",
        "name": "Planner foundation",
        "goal": "Create basic planner runtime.",
        "tasks": [
          {
            "id": "T1",
            "description": "Implement planner CLI",
            "files": [
              "agents/planner-agent/planner.py"
            ],
            "depends_on": [],
            "parallelizable": false,
            "details": [
              "Implement argument parsing.",
              "Build structured prompt.",
              "Invoke Codex."
            ],
            "acceptance_criteria": [
              "Planner accepts a task.",
              "Planner produces structured output."
            ]
          }
        ],
        "validation": [
          "Run planner with --dry-run."
        ]
      }
    ],
    "execution_groups": [
      {
        "name": "Foundation",
        "purpose": "Sequential base implementation.",
        "task_ids": [
          "T1"
        ]
      }
    ]
  },
  "testing": [
    "Validate generated JSON.",
    "Verify source tree remains unchanged."
  ],
  "risks": [
    {
      "risk": "Planner proposes duplicate functionality.",
      "mitigation": "Require repository inspection and code-map review."
    }
  ],
  "done_criteria": [
    "Plan JSON is valid.",
    "PLAN.md contains full implementation details."
  ]
}
```

---

# 14. JSON Schema Concept

Equivalent planner schema:

```json
{
  "type": "object",
  "required": [
    "title",
    "summary",
    "assumptions",
    "architecture",
    "implementation",
    "testing",
    "risks",
    "done_criteria"
  ],
  "properties": {
    "title": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "assumptions": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "architecture": {
      "type": "object",
      "required": [
        "overview",
        "tree",
        "components",
        "data_flow"
      ]
    },
    "implementation": {
      "type": "object",
      "required": [
        "phases",
        "execution_groups"
      ]
    },
    "testing": {
      "type": "array"
    },
    "risks": {
      "type": "array"
    },
    "done_criteria": {
      "type": "array"
    }
  }
}
```

The production version should use stricter nested definitions and `additionalProperties: false`.

---

# 15. Recommended Python Implementation

The initial implementation should stay compact.

Recommended conceptual source tree:

```text
agents/planner-agent/
├── planner.py
└── validation.py
```

Even though this document is intentionally a single specification file, the eventual runtime code may use these two Python files because they have distinct responsibilities.

---

# 16. `planner.py` Blueprint

```python
"""
Planner Agent CLI.

Builds a repository-aware structured planning prompt, invokes Codex CLI
in read-only mode, validates the returned plan, and writes reusable planning
artifacts without modifying application source files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from validation import validate_cli_inputs, validate_plan


AGENT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    """Parse planner CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Generate a structured implementation plan with Codex CLI."
    )

    parser.add_argument(
        "task",
        help="What should be planned.",
    )

    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root.",
    )

    parser.add_argument(
        "--context",
        default="",
        help="Additional planning context.",
    )

    parser.add_argument(
        "--output-dir",
        default=".agent-state/plans",
        help="Planning artifact directory.",
    )

    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI executable.",
    )

    parser.add_argument(
        "--model",
        default="",
        help="Optional Codex model override.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated prompt without executing Codex.",
    )

    return parser.parse_args()


def build_prompt(
    task: str,
    context: str,
    repo: Path,
    planner_instructions: str,
) -> str:
    """Build the repository-aware planning prompt."""

    context_text = context.strip() or "No additional user context supplied."

    return f"""
{planner_instructions}

# Current planning request

## Repository

{repo}

## User task

{task.strip()}

## Additional context

{context_text}

## Required behavior

- Inspect the repository before designing.
- Reuse existing code where possible.
- Read ARCHITECTURE.md and code-map.yaml when available.
- Keep architecture compact.
- Avoid unnecessary abstractions.
- Produce a tree-based architecture.
- Include detailed implementation phases.
- Include file-level changes.
- Include dependencies.
- Identify parallelizable tasks.
- Include tests.
- Include risks.
- Include definition of done.
- Planning only.
- Return structured JSON.
""".strip()


def run_codex(
    prompt: str,
    repo: Path,
    schema_path: Path,
    output_path: Path,
    codex_bin: str,
    model: str,
) -> None:
    """Invoke Codex CLI using a read-only sandbox."""

    command = [
        codex_bin,
        "exec",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
    ]

    if model:
        command.extend(
            [
                "--model",
                model,
            ]
        )

    command.append("-")

    result = subprocess.run(
        command,
        input=prompt,
        text=True,
        cwd=repo,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Codex planning execution failed."
        raise RuntimeError(error)

    if not output_path.exists():
        raise RuntimeError(
            "Codex finished without producing the expected structured plan."
        )


def render_plan_markdown(plan: dict) -> str:
    """Convert structured planner JSON into readable Markdown."""

    lines = [
        f"# {plan['title']}",
        "",
        plan["summary"],
        "",
        "## Assumptions",
    ]

    lines.extend(
        f"- {item}"
        for item in plan["assumptions"]
    )

    architecture = plan["architecture"]

    lines.extend(
        [
            "",
            "## Target Architecture",
            "",
            architecture["overview"],
            "",
            "```text",
            architecture["tree"],
            "```",
            "",
            "## Components",
        ]
    )

    for component in architecture["components"]:
        lines.extend(
            [
                "",
                f"### `{component['path']}`",
                "",
                component["purpose"],
                "",
                "Responsibilities:",
            ]
        )

        lines.extend(
            f"- {item}"
            for item in component["responsibilities"]
        )

    lines.extend(
        [
            "",
            "## Runtime Flow",
        ]
    )

    for index, step in enumerate(
        architecture["data_flow"],
        start=1,
    ):
        lines.append(
            f"{index}. {step}"
        )

    lines.extend(
        [
            "",
            "## Implementation Plan",
        ]
    )

    for phase in plan["implementation"]["phases"]:
        lines.extend(
            [
                "",
                f"### {phase['id']} — {phase['name']}",
                "",
                phase["goal"],
            ]
        )

        for task in phase["tasks"]:
            dependencies = ", ".join(
                task["depends_on"]
            ) or "none"

            lines.extend(
                [
                    "",
                    f"#### {task['id']} — {task['description']}",
                    "",
                    f"- Depends on: {dependencies}",
                    f"- Parallelizable: {task['parallelizable']}",
                    "",
                    "Implementation details:",
                ]
            )

            lines.extend(
                f"- {item}"
                for item in task["details"]
            )

            lines.append("")
            lines.append("Acceptance criteria:")

            lines.extend(
                f"- {item}"
                for item in task["acceptance_criteria"]
            )

    lines.extend(
        [
            "",
            "## Testing",
        ]
    )

    lines.extend(
        f"- {item}"
        for item in plan["testing"]
    )

    lines.extend(
        [
            "",
            "## Risks",
        ]
    )

    for risk in plan["risks"]:
        lines.append(
            f"- **{risk['risk']}** — {risk['mitigation']}"
        )

    lines.extend(
        [
            "",
            "## Definition of Done",
        ]
    )

    lines.extend(
        f"- {item}"
        for item in plan["done_criteria"]
    )

    return "\n".join(lines)


def main() -> int:
    """Execute the Planner Agent workflow."""

    args = parse_args()

    repo, output_base, codex_bin = validate_cli_inputs(
        repo=args.repo,
        output_dir=args.output_dir,
        codex_bin=args.codex_bin,
        dry_run=args.dry_run,
    )

    planner_instructions = load_planner_instructions()

    prompt = build_prompt(
        task=args.task,
        context=args.context,
        repo=repo,
        planner_instructions=planner_instructions,
    )

    if args.dry_run:
        print(prompt)
        return 0

    run_id = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    run_dir = output_base / run_id
    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    raw_plan_path = run_dir / "plan.json"

    run_codex(
        prompt=prompt,
        repo=repo,
        schema_path=get_schema_path(),
        output_path=raw_plan_path,
        codex_bin=codex_bin,
        model=args.model.strip(),
    )

    plan = json.loads(
        raw_plan_path.read_text(
            encoding="utf-8"
        )
    )

    validate_plan(plan)

    (run_dir / "prompt.md").write_text(
        prompt,
        encoding="utf-8",
    )

    (run_dir / "PLAN.md").write_text(
        render_plan_markdown(plan),
        encoding="utf-8",
    )

    print(
        f"Plan created: {run_dir / 'PLAN.md'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

# 17. Validation Blueprint

Validation should stay outside orchestration logic.

Conceptual `validation.py`:

```python
"""
Planner Agent validation.

Contains planner input and generated-plan validation.
"""

from __future__ import annotations

import shutil
from pathlib import Path


REQUIRED_PLAN_KEYS = {
    "title",
    "summary",
    "assumptions",
    "architecture",
    "implementation",
    "testing",
    "risks",
    "done_criteria",
}


def validate_cli_inputs(
    repo: str,
    output_dir: str,
    codex_bin: str,
    dry_run: bool,
) -> tuple[Path, Path, str]:
    """Validate Planner Agent runtime inputs."""

    repo_path = Path(
        repo
    ).expanduser().resolve()

    if not repo_path.is_dir():
        raise ValueError(
            f"Repository does not exist: {repo_path}"
        )

    output_path = Path(
        output_dir
    ).expanduser()

    if not output_path.is_absolute():
        output_path = repo_path / output_path

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    resolved_codex = shutil.which(
        codex_bin
    )

    if not dry_run and resolved_codex is None:
        raise ValueError(
            f"Codex executable not found: {codex_bin}"
        )

    return (
        repo_path,
        output_path.resolve(),
        resolved_codex or codex_bin,
    )


def validate_plan(
    plan: dict,
) -> None:
    """Validate the semantic structure returned by Codex."""

    missing = REQUIRED_PLAN_KEYS.difference(
        plan
    )

    if missing:
        raise ValueError(
            f"Missing required planner fields: {sorted(missing)}"
        )

    architecture = plan.get(
        "architecture",
        {},
    )

    if not architecture.get(
        "tree",
        "",
    ).strip():
        raise ValueError(
            "Planner output must include an architecture tree."
        )

    implementation = plan.get(
        "implementation",
        {},
    )

    phases = implementation.get(
        "phases",
        [],
    )

    if not phases:
        raise ValueError(
            "Planner output must include implementation phases."
        )

    task_ids = set()

    for phase in phases:
        for task in phase.get(
            "tasks",
            [],
        ):
            task_id = task.get(
                "id"
            )

            if not task_id:
                raise ValueError(
                    "Every task must have an ID."
                )

            if task_id in task_ids:
                raise ValueError(
                    f"Duplicate task ID: {task_id}"
                )

            task_ids.add(
                task_id
            )
```

---

# 18. Code Map

The Planner Agent should maintain a logical code map equivalent to:

```yaml
project: planner-agent

purpose: >
  Repository-aware, tree-first implementation planning
  through Codex CLI.

files:

  planner.py:

    summary: >
      Main Planner Agent CLI orchestration.

    functions:

      parse_args:
        summary: >
          Parse task, repository, context, output,
          Codex model, and dry-run arguments.

      build_prompt:
        summary: >
          Combine permanent planning instructions
          with the current user request.

      run_codex:
        summary: >
          Invoke Codex CLI using stdin,
          read-only repository access,
          and structured output.

      render_plan_markdown:
        summary: >
          Convert structured planner JSON into
          worker-readable Markdown.

      main:
        summary: >
          Execute the complete planner workflow.


  validation.py:

    summary: >
      Central planner input and generated-plan validation.

    functions:

      validate_cli_inputs:
        summary: >
          Validate repository, output path,
          and Codex CLI availability.

      validate_plan:
        summary: >
          Validate required plan sections,
          architecture tree,
          phases,
          and unique task IDs.


runtime_outputs:

  .agent-state/plans/<UTC-run-id>/prompt.md:

    summary: >
      Exact prompt sent to Codex.


  .agent-state/plans/<UTC-run-id>/plan.json:

    summary: >
      Machine-readable implementation plan.


  .agent-state/plans/<UTC-run-id>/PLAN.md:

    summary: >
      Human-readable and worker-agent-readable plan.
```

---

# 19. Tree-Based Planning Output Requirement

Every generated implementation plan should include a target tree.

Example:

```text
monorepo/
│
├── agents/
│   ├── agent-builder/
│   ├── agent-ui-builder/
│   └── planner-agent/
│
├── agent-runtime/
│   └── agent-monorepo/
│       ├── resolver.py
│       ├── bootstrap.py
│       └── semantic_search.py
│
├── workflow-orchestrator/
│   ├── orchestrator.py
│   └── workflow-orchestrator.yaml
│
├── packages/
│   └── ...
│
├── project-registry.yaml
├── ARCHITECTURE.md
└── code-map.yaml
```

For each proposed path the plan should explain:

```text
existing
modify
new
reuse
deprecated
remove
```

where relevant.

---

# 20. Detailed Implementation Plan

## Phase P1 — Planner Contract

### T1 — Define Planner Agent behavior

Document:

- purpose;
- read-only behavior;
- repository inspection requirements;
- reuse-first policy;
- output structure;
- dependency handling;
- parallelization rules.

### Acceptance

- Planner behavior is deterministic enough for downstream agents.
- Planner cannot silently become a coding agent.

---

### T2 — Define structured output

Planner JSON must include:

```text
title
summary
assumptions
architecture
  overview
  tree
  components
  data_flow
implementation
  phases
    tasks
      id
      files
      dependencies
      parallelizable
      details
      acceptance criteria
  execution groups
testing
risks
done criteria
```

### Acceptance

- Workflow Orchestrator can parse the output without extracting data from prose.

---

# 21. Phase P2 — Python Runtime

### T3 — Implement CLI input handling

Required support:

```text
task
repo
context
output-dir
codex-bin
model
dry-run
```

Avoid a configuration manager until configuration complexity actually requires one.

---

### T4 — Implement validation

Validate:

- repository exists;
- Codex CLI exists;
- planner schema exists;
- output directory is writable;
- generated JSON is valid;
- architecture tree exists;
- at least one implementation task exists;
- task IDs are unique.

---

### T5 — Implement prompt generation

The prompt should combine:

```text
planner instructions
+
repository location
+
user task
+
additional context
+
structured output requirements
```

The Planner Agent should explicitly instruct Codex to inspect the repository itself.

Do not attempt to serialize the entire repository into the prompt.

That wastes tokens and creates stale context.

Let Codex inspect the workspace directly.

---

### T6 — Implement Codex execution

Use:

```python
subprocess.run(...)
```

rather than introducing a custom process abstraction.

Run Codex from:

```text
cwd=<target repository>
```

Use:

```text
--sandbox read-only
```

The Planner Agent must not mutate application source.

---

# 22. Phase P3 — Planning Artifacts

Each planner execution creates:

```text
.agent-state/
└── plans/
    └── 20260910T054000Z/
        ├── prompt.md
        ├── plan.json
        └── PLAN.md
```

## `prompt.md`

Stores the exact planning prompt.

Useful for:

- debugging;
- evaluation;
- comparing planner behavior;
- future agent memory;
- reproducing a planning run.

## `plan.json`

Machine-readable source of truth.

Useful for:

- workflow orchestration;
- dependency graph creation;
- worker assignment;
- plan approval;
- plan revisions;
- progress tracking.

## `PLAN.md`

Human-readable plan.

Useful for:

- developer review;
- Claude Code;
- Codex workers;
- implementation agents;
- architectural review.

---

# 23. Phase P4 — Parallel Execution Model

The planner should not directly launch worker agents yet.

Instead it should describe execution groups.

Example:

```text
Execution Group 1
├── T1 architecture updates
└── T2 schema preparation

Execution Group 2
├── T3 backend implementation
├── T4 UI implementation
└── T5 tests

Execution Group 3
└── T6 integration validation
```

Only tasks without dependency relationships should be placed in the same parallel group.

Example JSON:

```json
{
  "execution_groups": [
    {
      "name": "parallel-foundation",
      "purpose": "Independent base work",
      "task_ids": [
        "T2",
        "T3"
      ]
    },
    {
      "name": "integration",
      "purpose": "Work requiring foundation completion",
      "task_ids": [
        "T4"
      ]
    }
  ]
}
```

---

# 24. Phase P5 — Resolver Integration

The Agent Resolver should eventually resolve:

```text
user prompt
    │
    ├── agent
    ├── skills
    ├── repository
    ├── context
    └── workflow
```

Example:

```text
"Create a UI debugger agent"
         │
         ▼
resolver.py
         │
         ├── planner-agent
         ├── python-development skill
         ├── selenium skill
         └── agent-building workflow
         │
         ▼
planner-agent
```

Then:

```text
plan.json
    │
    ▼
workflow-orchestrator
```

---

# 25. Phase P6 — Workflow Orchestration Integration

The future orchestrator can consume:

```json
{
  "task_id": "T4",
  "files": [
    "agents/ui-debugger/browser.py"
  ],
  "depends_on": [
    "T1"
  ],
  "parallelizable": true
}
```

The orchestrator can build a DAG:

```text
T1
├── T2
├── T3
└── T4
     │
     ▼
    T5
```

Later this can become:

```text
networkx DAG
or
custom lightweight dependency resolver
```

Do not introduce graph libraries initially unless dependency complexity actually requires them.

---

# 26. Planner and Agent Memory

The Planner Agent should initially rely on:

```text
repository
ARCHITECTURE.md
code-map.yaml
recent planning context
```

Later semantic memory can augment this.

Recommended future flow:

```text
Planner request
     │
     ▼
Semantic memory retrieval
     │
     ├── architecture decisions
     ├── previous failed approaches
     ├── reusable implementations
     └── previous related plans
     │
     ▼
Planner prompt
```

Semantic retrieval should be context augmentation, not the source of truth.

The current repository remains authoritative.

---

# 27. Planning Quality Rules

The Planner Agent should reject weak plans that merely say:

```text
1. Add backend.
2. Add frontend.
3. Test.
```

A good plan should instead say:

```text
T4 — Extend agent resolver

Files:
- agent-runtime/agent-monorepo/resolver.py
- project-registry.yaml
- code-map.yaml

Dependencies:
- T1

Implementation:
- reuse existing agent metadata loading;
- add planner-agent registration;
- return planner identity and resolved skill set;
- avoid adding a second registry implementation.

Acceptance:
- planner-agent resolves by name;
- existing agents still resolve unchanged;
- resolver tests pass.
```

---

# 28. Architecture Update Rules

If the implementation changes:

```text
file added
file removed
function added
function renamed
function moved
module responsibility changed
```

the plan must include:

```text
Update ARCHITECTURE.md
Update code-map.yaml
```

This is especially important for your agent system because workers need an accurate blueprint of the repository.

---

# 29. Code Map Maintenance Strategy

`code-map.yaml` should describe the current source tree, not historical changes.

Example:

```yaml
files:
  resolver.py:
    functions:
      resolve_agent:
        summary: Resolve an agent using project registry.
```

When a function changes:

```text
resolve_agent()
```

the worker updates the same code-map entry.

Do not append historical versions like:

```yaml
resolve_agent_v1
resolve_agent_old
resolve_agent_previous
```

Historical information belongs in interaction/event logs or Git history.

---

# 30. Planner Output Example

User:

```text
Create a UI debugger agent using Selenium that gathers console errors,
network failures, and visual layout issues.
```

Planner output should resemble:

```text
# UI Debugger Agent Plan

## Existing reusable modules

- agent-runtime/agent-monorepo/resolver.py
- existing agent registration
- shared logging
- shared validation

## Target architecture

monorepo/
├── agents/
│   └── ui-debugger/
│       ├── debugger.py
│       ├── browser.py
│       └── validation.py
│
├── agent-runtime/
│   └── agent-monorepo/
│       └── resolver.py
│
├── ARCHITECTURE.md
└── code-map.yaml

## T1 — Agent registration

Modify:
- project-registry.yaml
- resolver.py

## T2 — Selenium browser capture

Create:
- agents/ui-debugger/browser.py

Capture:
- console events
- JS exceptions
- network requests
- failed requests
- response status
- DOM snapshot
- viewport metadata

## T3 — Visual diagnostics

Use:
- bounding boxes
- overlap detection
- overflow detection
- font-size anomalies
- alignment comparison
- viewport clipping

## T4 — Codex analysis

Feed collected diagnostic data to Codex.

## T5 — Architecture synchronization

Update:
- ARCHITECTURE.md
- code-map.yaml
```

---

# 31. Testing Strategy

## Unit validation

Test:

- argument parsing;
- repository validation;
- Codex path validation;
- prompt generation;
- plan validation;
- duplicate task IDs;
- empty architecture tree.

---

## Integration validation

Use a sample repository containing:

```text
ARCHITECTURE.md
code-map.yaml
existing utility
existing service
```

Ask Planner Agent to add a feature.

Verify it:

- references existing architecture;
- reuses the existing service;
- does not create a duplicate service;
- identifies exact files;
- produces a tree;
- identifies dependencies.

---

# 32. Dry-Run Mode

Support:

```bash
python planner.py \
  "Build workflow orchestration" \
  --repo ~/monorepo \
  --dry-run
```

Expected behavior:

```text
print structured prompt
do not invoke Codex
do not create plan
do not modify repository
```

This is useful for prompt debugging.

---

# 33. Error Handling

Prefer clear errors.

Example:

```text
PlannerError:
Codex CLI executable 'codex' was not found.
```

Example:

```text
PlannerError:
Repository does not exist:
/Users/example/project
```

Example:

```text
PlannerError:
Generated plan does not contain an architecture tree.
```

Avoid swallowing errors or returning empty plans.

---

# 34. Logging

Initially, keep Planner Agent logging simple.

Recommended events:

```text
planner.request_received
planner.prompt_created
planner.codex_started
planner.codex_completed
planner.plan_validated
planner.plan_saved
planner.failed
```

Do not build a large observability framework in the first version.

Later these events can be sent to the shared agent logging system.

---

# 35. Security

Planner must execute Codex with:

```text
read-only repository access
```

Avoid:

```text
danger-full-access
full-auto implementation
automatic package installation
deployment commands
```

The planner's role is architectural planning.

Implementation belongs to worker agents.

---

# 36. Recommended Initial Architecture

For the first working version:

```text
Planner Agent
│
├── Python CLI
│
├── Structured prompt
│
├── Codex exec
│
├── Output JSON validation
│
└── PLAN.md rendering
```

Do not initially add:

```text
Flask API
FastAPI
Redis
DynamoDB
SQS
SNS
vector DB
workflow engine
graph database
plugin engine
message broker
```

Those belong to higher-level orchestration and memory systems.

---

# 37. Future Planner Extensions

After the basic Planner Agent is stable:

```text
planner-agent
│
├── repository context
├── semantic memory
├── web research when needed
├── architecture decision retrieval
├── previous-plan comparison
├── plan revision
├── execution DAG
└── worker handoff
```

Recommended order:

```text
1. Planner CLI
2. Structured output
3. Resolver integration
4. Workflow orchestrator integration
5. Shared logging
6. Semantic memory
7. Web research routing
8. Plan review/revision
9. Worker dispatch
```

---

# 38. Planner + Web Search

The Planner Agent should not automatically search the web for every task.

Recommended decision flow:

```text
Planning request
      │
      ▼
Can repository + existing knowledge answer it?
      │
 ┌────┴────┐
 │         │
Yes        No
 │         │
 ▼         ▼
Plan    Web research
          │
          ▼
     summarized evidence
          │
          ▼
         Plan
```

Use web search when:

- current library/API behavior matters;
- a technology is unfamiliar;
- current best practice materially affects the architecture;
- dependency versions or current standards matter.

Do not use web search for basic repository-local refactoring.

---

# 39. Planner + Skills

The Agent Resolver should resolve skills before Planner Agent execution.

Example:

```yaml
planner-agent:
  skills:
    - python-development
    - architecture-planning
    - codebase-analysis
```

For a UI debugger request:

```yaml
resolved_skills:
  - python-development
  - selenium-browser-automation
  - ui-debugging
  - architecture-planning
```

Those skills become part of the Planner Agent context.

---

# 40. Planner Agent Final Contract

## Input

```text
task
repository
optional context
resolved skills
resolved workflow
```

## Processing

```text
inspect repository
understand architecture
search reusable code
design compact solution
produce dependency-aware tasks
```

## Output

```text
plan.json
PLAN.md
prompt.md
```

## Must include

```text
architecture tree
components
runtime flow
files
functions
reuse strategy
implementation phases
tasks
dependencies
parallelization
testing
risks
acceptance criteria
definition of done
architecture/code-map updates
```

## Must not

```text
modify source
deploy infrastructure
invent unnecessary modules
create duplicate functionality
hide dependencies
produce vague implementation steps
```

---

# 41. Definition of Done for Planner Agent

The Planner Agent is complete when:

- a user can submit a planning request from the CLI;
- Codex runs against the target repository;
- Codex operates in read-only mode;
- the prompt requires repository inspection;
- structured JSON is generated;
- the output contains a tree architecture;
- implementation tasks identify files;
- dependencies are explicit;
- parallel work is identified;
- acceptance criteria are explicit;
- tests are included;
- risks and mitigations are included;
- architecture/code-map updates are included when applicable;
- a readable `PLAN.md` is generated;
- downstream workflow orchestration can consume `plan.json`;
- the Planner Agent itself remains compact and understandable.

---

# 42. Recommended Next Integration

After implementing this Planner Agent, integrate it into the monorepo in this order:

```text
User Prompt
   │
   ▼
Agent Gateway
   │
   ▼
Resolver
   │
   ├── agent
   ├── skills
   ├── workflow
   └── context
   │
   ▼
Planner Agent
   │
   ▼
plan.json
   │
   ▼
Workflow Orchestrator
   │
   ├── dependency graph
   ├── execution groups
   └── worker assignments
   │
   ▼
Worker Agents
   │
   ▼
Observer / Validator
   │
   ▼
Agent Logs / Memory
```

This keeps responsibilities separated while avoiding unnecessary complexity.
