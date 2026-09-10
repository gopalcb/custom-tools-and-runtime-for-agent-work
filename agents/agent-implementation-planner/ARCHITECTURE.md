# Architecture

## Purpose

The Implementation Planner Agent converts a non-trivial repository request
into a structured, read-only plan. Its declarative definition is used by the
shared runtime, while `planner.py` is the deterministic CLI for producing
planning artifacts directly.

## Project Structure

- `agent.yaml`: declarative runtime registration.
- `instructions.md`: planning-only behavioral contract.
- `planner.py`: builds the prompt, invokes the shared official Codex SDK façade
  in read-only mode, and writes the structured plan artifacts.
- `validation.py`: validates planner inputs and returned plan structure.
- `plan.schema.json`: JSON schema supplied to Codex CLI, including the selected
  execution `workflow_id`.

## Main Execution Flow

The CLI validates the repository and output location, loads this agent's
instructions, builds a repository-aware prompt, invokes the SDK with an
ephemeral read-only thread and output schema, validates the returned JSON, then
writes `prompt.md`, `plan.json`, and `PLAN.md` below
`.agent-state/plans/<run-id>/`.

## Extension Points

The shared runtime may invoke the declarative agent after context resolution
and optional runtime-provided web research. It selects a declared execution
workflow through `workflow_id`; the runtime accepts only catalogued execution
workflows. The standalone CLI remains read-only and does not apply the
generated plan.
