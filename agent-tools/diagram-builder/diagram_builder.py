"""
Render reusable architecture diagram components from declarative YAML.

This module owns YAML loading, payload validation, and HTML generation for the
diagram-builder tool. Styling and component names live under assets/.
"""

from argparse import ArgumentParser
from html import escape
from pathlib import Path

import yaml


DEFAULT_COMPONENTS = Path(__file__).parent / "assets" / "components.yaml"
DEFAULT_CSS = Path("assets/styles.css")


def load_yaml(path: Path) -> dict:
    """Load a YAML document from disk and return a dictionary payload."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"Unable to read YAML file: {path}") from error

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_component_catalog(path: Path) -> dict:
    """Load the reusable component catalog."""
    payload = load_yaml(path)
    components = payload.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError(f"Component catalog must contain a components mapping: {path}")
    return components


def validate_document(payload: dict, components: dict) -> dict:
    """Validate and normalize a diagram document."""
    diagrams = payload.get("diagrams")
    if not isinstance(diagrams, list) or not diagrams:
        raise ValueError("diagram YAML must include a non-empty diagrams list")

    for index, diagram in enumerate(diagrams):
        if not isinstance(diagram, dict):
            raise ValueError(f"diagram {index + 1} must be a mapping")

        diagram_type = diagram.get("type")
        if diagram_type not in {"flow", "tree", "event_bus"}:
            raise ValueError(f"diagram {index + 1} has unsupported type: {diagram_type}")

        if diagram_type == "flow":
            steps = diagram.get("steps")
            if not isinstance(steps, list) or not steps:
                raise ValueError(f"flow diagram {index + 1} must include steps")
            for step in steps:
                component = step.get("component") if isinstance(step, dict) else None
                if component not in components:
                    raise ValueError(f"unknown flow component: {component}")

        if diagram_type == "tree":
            if not isinstance(diagram.get("root"), dict):
                raise ValueError(f"tree diagram {index + 1} must include a root mapping")
            validate_tree_node(diagram["root"])

        if diagram_type == "event_bus":
            required = ["runtime", "sources", "hub", "outputs", "post_completion"]
            missing = [name for name in required if name not in diagram]
            if missing:
                raise ValueError(f"event_bus diagram {index + 1} missing: {', '.join(missing)}")
            if not isinstance(diagram["sources"], list) or not diagram["sources"]:
                raise ValueError(f"event_bus diagram {index + 1} sources must be a non-empty list")
            if not isinstance(diagram["outputs"], list) or not diagram["outputs"]:
                raise ValueError(f"event_bus diagram {index + 1} outputs must be a non-empty list")
            if not isinstance(diagram["post_completion"], dict):
                raise ValueError(f"event_bus diagram {index + 1} post_completion must be a mapping")

    return payload


def validate_tree_node(node: dict) -> None:
    """Validate one tree node and its descendants."""
    if not isinstance(node.get("name"), str) or not node["name"].strip():
        raise ValueError("tree nodes must include a non-empty name")

    children = node.get("children", [])
    if not isinstance(children, list):
        raise ValueError(f"tree node children must be a list: {node['name']}")

    for child in children:
        if not isinstance(child, dict):
            raise ValueError(f"tree child must be a mapping under: {node['name']}")
        validate_tree_node(child)


def render_label(component: str, text: str, components: dict) -> str:
    """Render a catalog-backed label component."""
    class_name = escape(components[component]["class"], quote=True)
    return f'<div class="{class_name}">{escape(text)}</div>'


def render_connector(step: dict, components: dict) -> str:
    """Render a down arrow connector with optional right-side branches."""
    component = step["component"]
    class_name = escape(components[component]["class"], quote=True)
    if component == "down-arrow":
        return f'<div class="{class_name}" aria-hidden="true"></div>'

    branches = step.get("branches", [])
    if not isinstance(branches, list):
        raise ValueError("down-arrow-with-right-branches branches must be a list")

    branch_rows = "\n".join(
        f'<li class="db-connector__branch">{escape(str(branch))}</li>'
        for branch in branches
    )
    return (
        f'<div class="{class_name}" aria-hidden="true">'
        '<div class="db-connector__spine"></div>'
        f'<ul class="db-connector__branches">{branch_rows}</ul>'
        "</div>"
    )


def render_flow(diagram: dict, components: dict) -> str:
    """Render a vertical flow diagram from reusable label and arrow units."""
    pieces = []
    for step in diagram["steps"]:
        component = step["component"]
        if component.startswith("label-"):
            pieces.append(render_label(component, str(step.get("text", "")), components))
        elif component.startswith("down-arrow"):
            pieces.append(render_connector(step, components))
        else:
            raise ValueError(f"flow component is not valid in this position: {component}")

    return '<div class="db-flow">' + "\n".join(pieces) + "</div>"


def render_tree_node(node: dict, components: dict, is_root: bool = False) -> str:
    """Render one recursive tree node."""
    name = escape(str(node.get("name", "")))
    children = node.get("children", [])
    node_type = "tree-root" if is_root else "tree-folder" if children else "tree-file"
    class_name = escape(components[node_type]["class"], quote=True)
    label = f'<span class="{class_name}">{name}</span>'

    if not children:
        return label

    child_items = "\n".join(
        f"<li>{render_tree_node(child, components)}</li>"
        for child in children
    )
    return f"{label}<ul>{child_items}</ul>"


def render_tree(diagram: dict, components: dict) -> str:
    """Render a repository-style tree diagram."""
    return '<div class="db-tree">' + render_tree_node(diagram["root"], components, True) + "</div>"


def render_event_bus(diagram: dict) -> str:
    """Render the event hub and post-completion architecture diagram."""
    source_positions = distribute_positions(len(diagram["sources"]), 22, 78)
    output_positions = distribute_positions(len(diagram["outputs"]), 34, 66)
    post_completion = diagram["post_completion"]
    artifacts = post_completion.get("artifacts", [])
    artifact_positions = distribute_positions(len(artifacts), 25, 75)
    metric_child = post_completion.get("metric_child")
    metric_x = artifact_positions[-1] if artifact_positions else 50

    source_nodes = "\n".join(
        render_positioned_node(str(source), "db-bus__source", source_positions[index], 22)
        for index, source in enumerate(diagram["sources"])
    )
    output_nodes = "\n".join(
        render_positioned_output(output, output_positions[index], 55)
        for index, output in enumerate(diagram["outputs"])
    )
    artifact_nodes = "\n".join(
        render_positioned_node(str(artifact), "db-bus__artifact", artifact_positions[index], 82)
        for index, artifact in enumerate(artifacts)
    )
    metric_node = ""
    if metric_child:
        metric_node = render_positioned_caption(str(metric_child), metric_x, 94)

    connector_svg = render_event_bus_connectors(
        source_positions,
        output_positions,
        artifact_positions,
        metric_x if metric_child else None,
    )

    return f"""
<div class="db-bus">
  {connector_svg}
  {render_positioned_node(str(diagram["runtime"]), "db-bus__runtime", 50, 6)}
  {source_nodes}
  {render_positioned_node(str(diagram["hub"]), "db-bus__hub", 50, 38)}
  {output_nodes}
  {render_positioned_node(str(post_completion.get("name", "PostCompletion")), "", 50, 70)}
  {artifact_nodes}
  {metric_node}
</div>
"""


def distribute_positions(count: int, start: int, end: int) -> list:
    """Distribute node x positions across a bounded horizontal range."""
    if count <= 0:
        return []
    if count == 1:
        return [50]

    step = (end - start) / (count - 1)
    return [round(start + step * index, 2) for index in range(count)]


def render_positioned_node(text: str, modifier: str, x: float, y: float) -> str:
    """Render an absolutely positioned event bus node."""
    classes = "db-bus__node"
    if modifier:
        classes = f"{classes} {modifier}"
    return (
        f'<div class="{escape(classes, quote=True)}" '
        f'style="--db-x:{x}%;--db-y:{y}%;">{escape(text)}</div>'
    )


def render_positioned_caption(text: str, x: float, y: float) -> str:
    """Render an absolutely positioned caption under an event bus node."""
    return (
        '<div class="db-bus__caption" '
        f'style="--db-x:{x}%;--db-y:{y}%;">{escape(text)}</div>'
    )


def render_positioned_output(output: dict, x: float, y: float) -> str:
    """Render one positioned event bus output and optional child subscriber."""
    if isinstance(output, str):
        return render_positioned_node(output, "db-bus__output", x, y)

    name = escape(str(output.get("name", "")))
    child = output.get("child")
    output_node = (
        '<div class="db-bus__node db-bus__output" '
        f'style="--db-x:{x}%;--db-y:{y}%;">{name}</div>'
    )
    if not child:
        return output_node

    return output_node + render_positioned_caption(str(child), x, y + 10)


def render_event_bus_connectors(
    source_positions: list,
    output_positions: list,
    artifact_positions: list,
    metric_x: float | None,
) -> str:
    """Render connector lines for the positioned event bus diagram."""
    source_lines = "\n".join(
        f'<line x1="{x}" y1="15" x2="{x}" y2="19" />'
        f'<line x1="{x}" y1="25" x2="{x}" y2="31" />'
        for x in source_positions
    )
    output_lines = "\n".join(
        f'<line x1="{x}" y1="47" x2="{x}" y2="52" />'
        for x in output_positions
    )
    artifact_lines = "\n".join(
        f'<line x1="{x}" y1="79" x2="{x}" y2="80" />'
        for x in artifact_positions
    )

    source_start = source_positions[0] if source_positions else 50
    source_end = source_positions[-1] if source_positions else 50
    output_start = output_positions[0] if output_positions else 50
    output_end = output_positions[-1] if output_positions else 50
    artifact_start = artifact_positions[0] if artifact_positions else 50
    artifact_end = artifact_positions[-1] if artifact_positions else 50
    metric_line = ""
    if metric_x is not None:
        metric_line = f'<line x1="{metric_x}" y1="84" x2="{metric_x}" y2="91" marker-end="url(#db-arrow)" />'

    return f"""
  <svg class="db-bus__connectors" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <marker id="db-arrow" viewBox="0 0 8 8" refX="4" refY="4" markerWidth="5" markerHeight="5" orient="auto">
        <path d="M0,0 L8,4 L0,8 Z" />
      </marker>
    </defs>
    <line x1="50" y1="9" x2="50" y2="15" />
    <line x1="{source_start}" y1="15" x2="{source_end}" y2="15" />
    {source_lines}
    <line x1="{source_start}" y1="31" x2="{source_end}" y2="31" />
    <line x1="50" y1="31" x2="50" y2="35" marker-end="url(#db-arrow)" />
    <line x1="50" y1="41" x2="50" y2="47" />
    <line x1="{output_start}" y1="47" x2="{output_end}" y2="47" />
    {output_lines}
    <line x1="50" y1="58" x2="50" y2="67" marker-end="url(#db-arrow)" />
    <line x1="50" y1="73" x2="50" y2="79" />
    <line x1="{artifact_start}" y1="79" x2="{artifact_end}" y2="79" />
    {artifact_lines}
    {metric_line}
  </svg>
"""


def render_diagram(diagram: dict, components: dict) -> str:
    """Render one diagram block by dispatching on its type."""
    title = diagram.get("title")
    heading = f'<h2 class="db-diagram__heading">{escape(str(title))}</h2>' if title else ""

    if diagram["type"] == "flow":
        body = render_flow(diagram, components)
    elif diagram["type"] == "tree":
        body = render_tree(diagram, components)
    else:
        body = render_event_bus(diagram)

    return f'<section class="db-diagram">{heading}{body}</section>'


def render_document(payload: dict, components: dict, css_href: str) -> str:
    """Render a complete HTML document for the provided diagram payload."""
    title = escape(str(payload.get("title", "Diagram Builder Output")))
    subtitle = payload.get("subtitle")
    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<p class="diagram-subtitle">{escape(str(subtitle))}</p>'

    diagram_html = "\n".join(render_diagram(diagram, components) for diagram in payload["diagrams"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <link rel="stylesheet" href="{escape(css_href, quote=True)}" />
</head>
<body>
  <main class="diagram-page">
    <div class="diagram-sheet">
      <h1 class="diagram-title">{title}</h1>
      {subtitle_html}
      {diagram_html}
    </div>
  </main>
</body>
</html>
"""


def build_parser() -> ArgumentParser:
    """Create the command-line parser for diagram rendering."""
    parser = ArgumentParser(description="Render YAML architecture diagrams to HTML.")
    parser.add_argument("input", type=Path, help="Path to the declarative YAML file.")
    parser.add_argument("output", type=Path, help="Path where HTML should be written.")
    parser.add_argument(
        "--components",
        type=Path,
        default=DEFAULT_COMPONENTS,
        help="Component catalog YAML path.",
    )
    parser.add_argument(
        "--css-href",
        default=str(DEFAULT_CSS),
        help="Stylesheet href to write into the HTML document.",
    )
    return parser


def main() -> None:
    """Load YAML input, render HTML, and write the output file."""
    parser = build_parser()
    args = parser.parse_args()
    components = load_component_catalog(args.components)
    payload = validate_document(load_yaml(args.input), components)
    html = render_document(payload, components, args.css_href)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
