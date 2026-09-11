# Diagram Builder

Diagram Builder converts declarative YAML into centered, transparent-background
HTML diagrams for blog posts and architecture articles.

## Render

```bash
.venv/bin/python agent-tools/diagram-builder/diagram_builder.py \
  agent-tools/diagram-builder/sample.yaml \
  agent-tools/diagram-builder/sample.html \
  --css-href assets/styles.css
```

Open `sample.html` in a browser. The generated page links to
`assets/styles.css`, so the HTML can sit beside the `assets/` directory.

## Component Units

Reusable unit names live in `assets/components.yaml` and are styled by
`assets/styles.css`.

- `label-upper`: uppercase milestone label.
- `label-normal`: primary process label.
- `label-lower`: lower-emphasis agent or leaf label.
- `down-arrow`: vertical down connector.
- `down-arrow-with-right-branches`: down connector with right-side branch rows.
- `tree-root`, `tree-folder`, `tree-file`: repository tree labels.
- `bus-source`, `bus-hub`, `bus-output`, `bus-artifact`: event pipeline nodes.

## YAML Shapes

Flow diagrams merge labels and connectors in order:

```yaml
type: flow
steps:
  - component: label-upper
    text: USER PROMPT
  - component: down-arrow
  - component: label-normal
    text: Agent Resolver
  - component: down-arrow-with-right-branches
    branches:
      - determine owner
```

Tree diagrams render nested `children`:

```yaml
type: tree
root:
  name: monorepo/
  children:
    - name: AGENTS.md
    - name: .agents/
      children:
        - name: skills/
```

Event bus diagrams render the aligned runtime, event hub, subscriber, and
post-completion artifact structure:

```yaml
type: event_bus
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
