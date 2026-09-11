# Architecture

## Purpose

Diagram Builder turns declarative YAML into small, reusable HTML architecture
diagrams for articles and blog posts. It focuses on transparent-background
components that can be embedded into pages with different surrounding themes.

## Project Structure

```text
diagram_builder.py
CLI entry point, YAML validation, and HTML rendering.

assets/components.yaml
Named component catalog used by YAML diagrams.

assets/styles.css
Reusable diagram styles based on the layout-builder theme tokens.

sample.yaml
Declarative examples for flow, tree, and runtime event diagrams.

sample.html
Generated HTML output from sample.yaml.
```

## Main Execution Flow

The CLI reads a YAML input file, loads `assets/components.yaml`, validates that
each diagram uses known component names and required fields, renders HTML, and
writes the output path. The generated document links to `assets/styles.css` by
default so it can be published with the CSS beside it.

## Module Responsibilities

- `diagram_builder.py`: owns loading YAML, validating the supported diagram
  shapes, rendering flow/tree/event bus diagrams, and writing HTML.
- `assets/components.yaml`: names reusable diagram units and their CSS classes.
- `assets/styles.css`: owns all visual styling and keeps outer diagram
  backgrounds transparent.

## Configuration

Input documents use a root `diagrams` list. Supported diagram types are `flow`,
`tree`, and `event_bus`. The CLI accepts `--components` for an alternate
catalog and `--css-href` for the stylesheet link written into generated HTML.

## Data Flow

YAML input and component catalog are loaded into dictionaries, validated, and
rendered into static HTML. The renderer does not execute scripts or fetch
remote assets.

## Extension Points

Add new unit names to `assets/components.yaml`, add the matching CSS in
`assets/styles.css`, then extend `diagram_builder.py` validation and rendering
when the new component requires behavior beyond a normal label or connector.
