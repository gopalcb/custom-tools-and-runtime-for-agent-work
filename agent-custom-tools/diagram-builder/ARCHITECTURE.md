# Architecture

## Purpose

The diagram builder renders compact, transparent-background HTML diagrams from
declarative YAML. It gives agents reusable primitives for explaining workflow,
runtime, event, tree, and architecture-component relationships without drawing
custom markup each time.

## Project Structure

`diagram_builder.py` owns YAML loading, validation, and HTML rendering.
`main.py` is a thin CLI facade.
`libs/components.yaml` is the component catalog.
`assets/styles.css` contains the shared visual system.
`sample-new-components.yaml` and `sample-new-components.html` verify compact
component variants.
`architecture-combinations.yaml` and `architecture-combinations-alt.yaml`
generate complete multi-component architecture examples.
`assets-view.html` is a hand-authored interactive catalog for browsing every
component in sequence.
`test.py` is the local smoke check.

## Main Execution Flow

The CLI reads an input YAML file, loads `libs/components.yaml`, validates each
diagram block, renders HTML sections for each diagram type, and writes the final
HTML document. Generated pages reference `assets/styles.css`.

## Module Responsibilities

`diagram_builder.py` keeps validation close to rendering because the supported
YAML schema is intentionally small. Flow, tree, event bus, component, component
stack, and component gallery rendering are separate functions in that file.

`main.py` only delegates to `diagram_builder.main()`.

`test.py` loads the sample YAML, validates it, renders it in memory, and checks
that the expected static component families appear.

## Configuration

The default catalog is `libs/components.yaml`. Callers can pass a different
catalog with `--components` and can choose the stylesheet href with
`--css-href`.

## Data Flow

YAML input describes high-level diagram intent. The component catalog maps names
to CSS classes and descriptions. The renderer validates the requested component
names and node counts, then emits HTML that the stylesheet turns into the final
diagram.

## Extension Points

Add new static primitives by updating `libs/components.yaml`, adding their
renderer support in `diagram_builder.py`, adding CSS in `assets/styles.css`, and
covering them in `sample-new-components.yaml` or an architecture combination
YAML.
