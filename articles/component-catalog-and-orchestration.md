# Component Catalog and Orchestration Details

This article documents the available diagram-builder components and how they
fit together.

The builder has one main job: turn clear YAML into clean HTML diagrams. It works
best when each diagram chooses the smallest component that explains the idea.

Generated diagrams for this article:

- [component-catalog-and-orchestration-diagrams.html](component-catalog-and-orchestration-diagrams.html)
- [component-catalog-and-orchestration-diagrams.yaml](component-catalog-and-orchestration-diagrams.yaml)

## Main Diagram Types

The builder supports six diagram types.

`flow` is for steps. Use it when the reader should move from top to bottom.

`tree` is for file or ownership structure. Use it when nesting matters.

`event_bus` is for runtime movement. Use it when several sources feed a hub and
produce outputs.

`component` is for one reusable unit.

`component_stack` is for a larger picture made from reusable units.

`component_gallery` is for showing the available architecture components in one
guide.

## Core Flow Components

Flow diagrams use labels and connectors:

- `label-upper`: a strong phase label.
- `label-normal`: a normal process label.
- `label-lower`: a quieter leaf or detail label.
- `down-arrow`: a simple vertical connector.
- `down-arrow-with-right-branches`: a vertical connector with side notes.

These are useful for routing, planning, validation, and article explanations.

## Tree Components

Tree diagrams are built from:

- `tree-root`
- `tree-folder`
- `tree-file`

You do not usually call these directly. You write nested YAML with `children`,
and the renderer chooses the correct tree component.

## Event Bus Components

Event-bus diagrams describe movement through a central hub:

- `bus-source`: inputs above the hub.
- `bus-hub`: the central event hub.
- `bus-output`: outputs below the hub.
- `bus-artifact`: post-completion artifacts.

This is useful for runtime diagrams because it keeps sources, hub, outputs, and
final artifacts in one readable shape.

## Architecture Components

Architecture components are fixed reusable units:

- `node-only`: one plain rectangle.
- `tri-node-component`: three nodes fed by a top rail and merged below.
- `double-node-component`: two nodes fed by a top rail and merged below.
- `node-with-up-down-arrow`: one node with incoming and outgoing arrows.
- `node-with-down-arrow`: one source node with a bottom arrow.
- `node-with-top-arrow`: one sink node with a top arrow.
- `tri-node-without-bottom-line`: three nodes with a top rail and optional
  per-node down arrows.
- `double-node-without-bottom-line`: two nodes with a top rail and optional
  per-node down arrows.

These are best for vertical architecture diagrams.

## Horizontal and Square Components

The compact library adds peer-style and state-style components:

- `horizontal-right-arrow`: left-to-right relationship.
- `horizontal-left-arrow`: right-to-left relationship.
- `horizontal-two-way-arrow`: bidirectional relationship.
- `animated-horizontal-right-arrow`: moving left-to-right flow.
- `animated-horizontal-left-arrow`: moving right-to-left flow.
- `animated-horizontal-two-way-arrow`: moving bidirectional flow.
- `square-with-text`: compact state or concept.
- `square-with-icon-detail`: compact state or concept with a badge and detail.

Node mappings can include:

- `text`
- `icon`
- `detail`
- `size`: `sm`, `md`, or `lg`
- `color`: `green`, `blue`, `red`, `yellow`, or `neutral`
- `style`: `soft`, `strong`, `outline`, or `dashed`

## Orchestration

The orchestration is intentionally small.

First, YAML declares the diagram type and data.

Second, the renderer validates the diagram. It checks that the diagram type is
supported, the component exists, and the node count is correct.

Third, the renderer turns the YAML into HTML.

Fourth, CSS gives the components stable geometry, colors, connector lines, and
animation.

This keeps the authoring path direct:

```text
YAML -> validation -> HTML -> CSS-rendered diagram
```

## Composition Rules

Use `node-only` above and below compound components when the compound component
already owns the arrows.

Use `tri-node-component` when three ideas meet.

Use `double-node-component` when two ideas meet.

Use `without-bottom-line` variants when outputs do not all rejoin.

Use horizontal arrows when the relationship is peer-to-peer instead of
top-to-bottom.

Use square nodes for states, modes, and small concepts.

Use event-bus diagrams when runtime sources feed a shared hub.

Use tree diagrams when names and nesting matter more than flow.

The simple rule is: choose the shape that matches the thought.
