# How the Implementation Planner Agent Works

## Purpose

The Implementation Planner Agent converts a non-trivial repository request into
a structured, read-only plan that downstream implementation agents can execute.
It does not modify source code. It decides what should be changed, why, in what
order, and how the result should be validated.

## Source Files

```text
agent-config/agents/agent-implementation-planner/
  agent.yaml
  instructions.md
  plan.schema.json
  planner.py
  validation.py
  ARCHITECTURE.md
  code-map.yaml
```

Key files:

- `agent.yaml`: declarative runtime registration.
- `instructions.md`: planning-only behavior contract.
- `plan.schema.json`: required JSON shape for runtime plans.
- `planner.py`: standalone read-only CLI planner.
- `validation.py`: validates planner inputs and returned plan structure.

## Runtime Invocation

For normal requests, the resolver selects the default `agent-monorepo` behavior
and the planning workflow runs first unless the user explicitly asks to skip
planning.

Planning workflow:

```text
pre-work-health -> analyze -> resolve-context -> optional web-research -> plan
```

The `plan` step invokes `agent-implementation-planner` as a Codex agent. The
runtime passes:

- implementation planner instructions;
- selected repository context;
- retrieved project memory;
- optional web research results;
- allowed tools and validation commands;
- the list of available execution workflow ids.

The planner must choose one available execution workflow in the JSON
`workflow_id` field.

## Planner Output Contract

The output must match `plan.schema.json` and include:

- `workflow_id`;
- `title`;
- `summary`;
- `assumptions`;
- `tasks`;
- `architecture`;
- `implementation`;
- `testing`;
- `risks`;
- `done_criteria`.

Each tracked task must include:

- stable lowercase dash-separated `name`;
- title;
- description;
- affected files;
- dependencies;
- acceptance criteria.

Use one tracked task unless splitting the work creates independently useful
implementation and review boundaries.

## How Runtime Uses the Plan

After the planner returns:

1. Runtime parses the structured JSON plan.
2. Runtime accepts only a `workflow_id` that exists in the declared execution
   workflows.
3. If the plan contains tracked tasks, runtime persists them under:

   ```text
   agent-runtime/controller-data-store/planned-tasks/<plan-title>/
     tasks.yaml
     <task-name>.md
   ```

4. Runtime emits an `artifact.created` event for the persisted plan tasks.
5. Runtime stores a planned-task handoff in the run context.
6. The selected execution workflow starts.
7. The next implementation agent step receives the planned-task handoff in its
   prompt.
8. Final reported lines such as:

   ```text
   planned-task <identifier>: complete
   ```

   update matching task YAML status for controller visibility.

## Standalone CLI Mode

The planner can also run through its deterministic CLI. In that mode it:

1. validates repository and output paths;
2. loads planner instructions;
3. builds a repository-aware prompt;
4. invokes the shared Codex SDK facade in read-only mode;
5. validates the returned JSON;
6. writes artifacts below:

   ```text
   .agent-state/plans/<run-id>/
     prompt.md
     plan.json
     PLAN.md
   ```

7. writes tracked task files under:

   ```text
   agent-runtime/controller-data-store/planned-tasks/<plan-title>/
   ```

The standalone planner remains read-only with respect to application source.

## Important Boundaries

- The planner proposes; implementation agents execute.
- The planner must inspect current source and project context before designing.
- Current source beats stale memory if they disagree.
- Web research is supplied by the runtime only when needed; the planner should
  not perform extra research itself.
- Python structure changes must include `ARCHITECTURE.md` and `code-map.yaml`
  synchronization work in the plan.
- The runtime is responsible for accepting or rejecting the chosen workflow id.

## Validation

After planner changes:

```bash
.venv/bin/python -m compileall agent-config/agents/agent-implementation-planner agent-runtime/agent-monorepo
.venv/bin/python -m pytest -q tests/test_default_configuration.py tests/test_planned_tasks.py tests/test_resolver.py
```
