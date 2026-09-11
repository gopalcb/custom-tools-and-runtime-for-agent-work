---
name: diagram-builder
description: Build transparent-background HTML diagrams with agent-tools/diagram-builder when the requested output is an HTML file, including flow, tree, and runtime/event architecture diagrams.
---

# Diagram Builder

Use this skill only when the user wants diagram output as HTML. Typical triggers:

- The prompt starts with `/diag-builder`.
- The user asks to use diagram builder.
- The user asks to create, build, render, or generate a diagram and the expected
  output is an HTML file.
- The user asks for an article or blog page and specifically asks for a diagram
  in the HTML output.

Do not use this skill when the requested output is a Markdown document or saved
article, such as `article.md`, `README.md`, `docs/topic.md`, or "save this as a
markdown file". In that case, write the Markdown normally and do not invoke the
HTML diagram builder.

## Tool Location

- Renderer: `agent-tools/diagram-builder/diagram_builder.py`
- Component catalog: `agent-tools/diagram-builder/assets/components.yaml`
- Styles: `agent-tools/diagram-builder/assets/styles.css`
- Example input: `agent-tools/diagram-builder/sample.yaml`
- Example output: `agent-tools/diagram-builder/sample.html`

## Supported Diagram Types

### Flow

Use `type: flow` for sequential architecture or workflow diagrams. Compose the
flow from small units:

- `label-upper`: uppercase milestone such as `USER PROMPT`.
- `label-normal`: normal process node such as `Agent Resolver`.
- `label-lower`: lower-emphasis leaf or selected agent.
- `down-arrow`: vertical connector.
- `down-arrow-with-right-branches`: vertical connector with right-side branch
  rows.

Example:

```yaml
type: flow
title: Agent routing flow
steps:
  - component: label-upper
    text: USER PROMPT
  - component: down-arrow
  - component: label-normal
    text: Agent Resolver
  - component: down-arrow-with-right-branches
    branches:
      - determine owner
      - choose workflow
```

### Tree

Use `type: tree` for repository and folder diagrams. Parent nodes render as
plain text, not boxes. Use nested `children` mappings.

```yaml
type: tree
title: Repository tree
root:
  name: monorepo/
  children:
    - name: AGENTS.md
    - name: agent-config/
      children:
        - name: skills/
```

### Event Bus

Use `type: event_bus` for runtime pipelines with a source row, central hub,
outputs, post-completion artifacts, and optional metric child. The renderer
uses positioned nodes plus SVG connectors, so keep labels short.

```yaml
type: event_bus
title: Runtime event pipeline
runtime: Agent Runtime
sources: [model events, tool events, workflow events]
hub: EventHub
outputs:
  - name: events.jsonl
  - name: live subscribers
    child: Codex Agent Console
post_completion:
  name: PostCompletion
  artifacts: [run.json, summary.md, metrics]
  metric_child: memory candidates
```

## Required Workflow

1. Confirm the requested artifact is HTML. If the user asks for Markdown output,
   do not use this skill.
2. Read `agent-tools/diagram-builder/README.md`,
   `agent-tools/diagram-builder/ARCHITECTURE.md`, and
   `agent-tools/diagram-builder/code-map.yaml` before changing the tool.
3. Create or update a declarative YAML file for the requested diagram.
4. Reuse existing components before adding new ones.
5. If a new component is needed, update all of:
   `assets/components.yaml`, `assets/styles.css`, renderer validation/rendering
   when necessary, `README.md`, and `code-map.yaml` if Python functions change.
6. Render with:

```bash
.venv/bin/python agent-tools/diagram-builder/diagram_builder.py \
  <input.yaml> \
  <output.html> \
  --css-href assets/styles.css
```

7. Run focused verification:

```bash
.venv/bin/python -m pytest -q tests/test_diagram_builder.py
```

8. For Python renderer changes, also run py_compile or compileall on
   `agent-tools/diagram-builder`.

## Design Rules

- Keep the generated page centered and transparent around diagram components.
- Follow `application-systems/layout-builder/theme/theme-library.html` tokens:
  muted green accent, warm neutral surfaces, small radius, restrained shadows,
  and readable compact text.
- Keep tree parent nodes as text only. Do not put root or folder labels in
  rectangle boxes.
- Keep event-pipeline connector lines visible enough for blog screenshots.
- Prefer static HTML/CSS. Do not add JavaScript unless the user explicitly asks
  for interactivity.
- Keep output portable: relative CSS link, no remote assets, no build step.
