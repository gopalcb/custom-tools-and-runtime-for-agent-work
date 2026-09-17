"""
Render reusable architecture diagram components from declarative YAML.

This module owns YAML loading, payload validation, and HTML generation for the
diagram-builder tool. Styling and component names live under assets/.
"""

from argparse import ArgumentParser
from html import escape
from pathlib import Path

import yaml


DEFAULT_COMPONENTS = Path(__file__).parent / "libs" / "components.yaml"
DEFAULT_CSS = Path("assets/styles.css")
ARCHITECTURE_COMPONENTS = {
    "node-only": 1,
    "square-with-text": 1,
    "square-with-icon-detail": 1,
    "tri-node-component": 3,
    "double-node-component": 2,
    "node-with-up-down-arrow": 1,
    "node-with-down-arrow": 1,
    "node-with-top-arrow": 1,
    "tri-node-without-bottom-line": 3,
    "double-node-without-bottom-line": 2,
    "horizontal-right-arrow": 2,
    "horizontal-left-arrow": 2,
    "horizontal-two-way-arrow": 2,
    "animated-horizontal-right-arrow": 2,
    "animated-horizontal-left-arrow": 2,
    "animated-horizontal-two-way-arrow": 2,
}
COMPONENT_USAGE_DETAILS = [
    {
        "component": "node-only",
        "title": "node-only",
        "detail": "Plain rectangle. Use above or below compact compound components so the compound unit owns the connector arrows.",
        "nodes": ["Plain node"],
    },
    {
        "component": "square-with-text",
        "title": "square-with-text",
        "detail": "Compact square label for small concepts, states, or endpoints.",
        "nodes": [{"text": "State", "detail": "ready", "color": "blue"}],
    },
    {
        "component": "square-with-icon-detail",
        "title": "square-with-icon-detail",
        "detail": "Square label with an icon, title, and short explanation.",
        "nodes": [{"icon": "T", "text": "Tools", "detail": "local calls", "style": "strong"}],
    },
    {
        "component": "tri-node-component",
        "title": "tri-node-component",
        "detail": "Three-node fan-in/fan-out. In a stack, the rectangle above and below this component should usually be node-only.",
        "nodes": ["model events", "tool events", "workflow events"],
    },
    {
        "component": "double-node-component",
        "title": "double-node-component",
        "detail": "Two-node fan-in/fan-out. It draws the top incoming stem and bottom outgoing arrow itself.",
        "nodes": ["events.jsonl", "live subscribers"],
    },
    {
        "component": "node-with-up-down-arrow",
        "title": "node-with-up-down-arrow",
        "detail": "Single standalone node with one incoming top arrow and one outgoing down arrow.",
        "nodes": ["EventHub"],
    },
    {
        "component": "node-with-down-arrow",
        "title": "node-with-down-arrow",
        "detail": "Standalone source node when only the next thing below needs to be reached.",
        "nodes": ["Agent Runtime"],
    },
    {
        "component": "node-with-top-arrow",
        "title": "node-with-top-arrow",
        "detail": "Standalone sink node when only an incoming top arrow is needed.",
        "nodes": ["Finalizer"],
    },
    {
        "component": "tri-node-without-bottom-line",
        "title": "tri-node-without-bottom-line",
        "detail": "Three nodes with top rail only. Add down_arrow on selected nodes when only some outputs continue.",
        "nodes": ["run.json", "summary.md", {"text": "metrics", "down_arrow": True, "down_label": "memory candidates"}],
    },
    {
        "component": "double-node-without-bottom-line",
        "title": "double-node-without-bottom-line",
        "detail": "Two nodes with top rail only. Add down_arrow to either or both outputs as needed.",
        "nodes": ["events.jsonl", {"text": "live subscribers", "down_arrow": True, "down_label": "Codex Agent Console"}],
    },
    {
        "component": "horizontal-right-arrow",
        "title": "horizontal-right-arrow",
        "detail": "Two horizontal nodes connected left-to-right.",
        "nodes": ["Input", "Output"],
    },
    {
        "component": "horizontal-left-arrow",
        "title": "horizontal-left-arrow",
        "detail": "Two horizontal nodes connected right-to-left.",
        "nodes": ["Consumer", "Source"],
    },
    {
        "component": "horizontal-two-way-arrow",
        "title": "horizontal-two-way-arrow",
        "detail": "Two horizontal nodes connected in both directions.",
        "nodes": [{"text": "Agent", "icon": "A"}, {"text": "Runtime", "icon": "R"}],
    },
]


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
    """Load the reusable component catalog from one YAML file or a directory."""
    if path.is_dir():
        components = {}
        for catalog_path in sorted(path.glob("*.yaml")):
            if catalog_path.name == "components.yaml":
                continue
            payload = load_yaml(catalog_path)
            catalog = payload.get("components")
            if not catalog:
                continue
            if not isinstance(catalog, dict):
                raise ValueError(f"Component catalog must contain a components mapping: {catalog_path}")
            duplicate_names = sorted(set(components).intersection(catalog))
            if duplicate_names:
                raise ValueError(
                    f"Duplicate component names in {catalog_path}: {', '.join(duplicate_names)}"
                )
            components.update(catalog)
        if not components:
            raise ValueError(f"Component catalog directory contains no components: {path}")
        return components

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
        if diagram_type not in {"flow", "tree", "event_bus", "component", "component_stack", "component_gallery"}:
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

        if diagram_type == "component":
            validate_architecture_component(diagram, index + 1)

        if diagram_type == "component_stack":
            blocks = diagram.get("components")
            if not isinstance(blocks, list) or not blocks:
                raise ValueError(f"component_stack diagram {index + 1} components must be a non-empty list")
            for block_index, block in enumerate(blocks):
                if not isinstance(block, dict):
                    raise ValueError(f"component_stack block {block_index + 1} must be a mapping")
                validate_architecture_component(block, index + 1)

    return payload


def validate_architecture_component(diagram: dict, diagram_number: int) -> None:
    """Validate one reusable architecture component diagram."""
    component = diagram.get("component")
    if component not in ARCHITECTURE_COMPONENTS:
        raise ValueError(f"component diagram {diagram_number} has unsupported component: {component}")

    nodes = diagram.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError(f"component diagram {diagram_number} nodes must be a list")

    expected_count = ARCHITECTURE_COMPONENTS[component]
    if len(nodes) != expected_count:
        raise ValueError(
            f"{component} requires exactly {expected_count} node"
            f"{'' if expected_count == 1 else 's'}"
        )

    for node in nodes:
        if isinstance(node, str):
            continue
        if not isinstance(node, dict):
            raise ValueError(f"{component} nodes must be strings or mappings")
        if not isinstance(node.get("text"), str) or not node["text"].strip():
            raise ValueError(f"{component} mapped nodes must include non-empty text")


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


def render_architecture_component(diagram: dict, diagram_id: int) -> str:
    """Render a reusable architecture component with fixed, precise geometry."""
    component = diagram["component"]
    nodes = normalize_component_nodes(diagram["nodes"])
    count = ARCHITECTURE_COMPONENTS[component]
    x_positions = component_positions(count)
    class_names = ["db-component", f"db-component--{component}"]
    if diagram.get("compact"):
        class_names.append("db-component--compact")

    connector_svg = render_component_connectors(component, x_positions, nodes)
    node_html = "\n".join(
        render_component_node(node, x_positions[index], component)
        for index, node in enumerate(nodes)
    )
    caption_html = "\n".join(
        render_component_caption(node, x_positions[index])
        for index, node in enumerate(nodes)
        if node.get("down_label")
    )

    return (
        f'<div class="{escape(" ".join(class_names), quote=True)}">'
        f"{connector_svg}\n{node_html}\n{caption_html}</div>"
    )


def render_component_stack(diagram: dict, diagram_id: int) -> str:
    """Render several reusable architecture components as one diagram."""
    blocks = "\n".join(
        render_architecture_component(block, (diagram_id * 100) + index)
        for index, block in enumerate(diagram["components"], start=1)
    )
    return f'<div class="db-component-stack">{blocks}</div>'


def render_component_gallery(diagram_id: int) -> str:
    """Render a review gallery for all architecture components."""
    items = []
    for index, entry in enumerate(COMPONENT_USAGE_DETAILS, start=1):
        component = {
            "component": entry["component"],
            "compact": True,
            "nodes": entry["nodes"],
        }
        preview = render_architecture_component(component, (diagram_id * 100) + index)
        items.append(
            '<article class="db-component-guide__item">'
            f'<h3 class="db-component-guide__name">{escape(entry["title"])}</h3>'
            f'<p class="db-component-guide__detail">{escape(entry["detail"])}</p>'
            f"{preview}</article>"
        )
    return '<div class="db-component-guide">' + "\n".join(items) + "</div>"


def normalize_component_nodes(nodes: list) -> list:
    """Normalize string and mapping node payloads into dictionaries."""
    normalized = []
    for node in nodes:
        if isinstance(node, str):
            normalized.append({"text": node})
            continue

        normalized.append(
            {
                "text": str(node["text"]),
                "icon": str(node["icon"]) if node.get("icon") else "",
                "detail": str(node["detail"]) if node.get("detail") else "",
                "size": str(node["size"]) if node.get("size") else "",
                "color": str(node["color"]) if node.get("color") else "",
                "style": str(node["style"]) if node.get("style") else "",
                "down_arrow": bool(node.get("down_arrow")),
                "down_label": str(node["down_label"]) if node.get("down_label") else "",
            }
        )
    return normalized


def component_positions(count: int) -> list:
    """Return stable x positions for one-, two-, and three-node components."""
    if count == 1:
        return [50]
    if count == 2:
        return [27, 73]
    return [16, 50, 84]


def render_component_node(node: dict, x: float, component: str) -> str:
    """Render one architecture component node."""
    y = 50
    if component == "node-with-up-down-arrow":
        y = 51
    if component.startswith("horizontal"):
        y = 50
    classes = ["db-component__node"]
    if component.startswith("square"):
        classes.append("db-component__node--square")
    for key in ("size", "color", "style"):
        value = node.get(key)
        if value:
            classes.append(f"db-component__node--{key}-{css_token(value)}")
    icon = f'<span class="db-component__icon">{escape(node["icon"])}</span>' if node.get("icon") else ""
    detail = f'<span class="db-component__detail">{escape(node["detail"])}</span>' if node.get("detail") else ""
    return (
        f'<div class="{escape(" ".join(classes), quote=True)}" '
        f'style="--db-x:{x}%;--db-y:{y}%;">'
        f'{icon}<span class="db-component__text">{escape(node["text"])}</span>{detail}</div>'
    )


def render_component_caption(node: dict, x: float) -> str:
    """Render a caption beneath a component node down arrow."""
    return (
        '<div class="db-component__caption" '
        f'style="--db-x:{x}%;--db-y:91%;">{escape(node["down_label"])}</div>'
    )


def render_component_connectors(
    component: str,
    x_positions: list,
    nodes: list,
) -> str:
    """Render SVG connector geometry for a reusable component."""
    if component in {"node-only", "square-with-text", "square-with-icon-detail"}:
        return ""

    arrow_heads = []
    if component in {
        "horizontal-right-arrow",
        "horizontal-left-arrow",
        "horizontal-two-way-arrow",
        "animated-horizontal-right-arrow",
        "animated-horizontal-left-arrow",
        "animated-horizontal-two-way-arrow",
    }:
        lines, arrow_heads = render_horizontal_connector(component, x_positions)
    elif component in {"tri-node-component", "double-node-component"}:
        top, top_heads = render_top_connector_lines(x_positions)
        bottom, bottom_heads = render_bottom_connector_lines(x_positions)
        arrow_heads.extend(top_heads)
        arrow_heads.extend(bottom_heads)
        lines = f"{top}\n{bottom}"
    elif component in {"tri-node-without-bottom-line", "double-node-without-bottom-line"}:
        top, top_heads = render_top_connector_lines(x_positions)
        arrow_heads.extend(top_heads)
        node_arrow_lines = []
        for x, node in zip(x_positions, nodes):
            if node.get("down_arrow"):
                node_arrow_lines.append(render_component_arrow_line(x, 60, 78))
                arrow_heads.append(render_component_arrowhead(x, 78))
        node_arrows = "\n".join(node_arrow_lines)
        lines = f"{top}\n{node_arrows}"
    elif component == "node-with-up-down-arrow":
        lines = (
            f"{render_component_arrow_line(50, 4, 39)}\n"
            f"{render_component_arrow_line(50, 61, 84)}"
        )
        arrow_heads.extend([render_component_arrowhead(50, 39), render_component_arrowhead(50, 84)])
    elif component == "node-with-top-arrow":
        lines = render_component_arrow_line(50, 8, 39)
        arrow_heads.append(render_component_arrowhead(50, 39))
    else:
        lines = render_component_arrow_line(50, 60, 88)
        arrow_heads.append(render_component_arrowhead(50, 88))

    arrow_head_html = "\n".join(arrow_heads)
    return f"""
  <svg class="db-component__connectors" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
{lines}
  </svg>
{arrow_head_html}"""


def render_component_arrow_line(x: float, y1: float, y2: float) -> str:
    """Render one vertical arrow shaft."""
    return f'    <line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" />'


def render_component_arrowhead(x: float, y: float) -> str:
    """Render one CSS-border arrowhead matching db-connector arrows."""
    return (
        '<span class="db-component__arrowhead" aria-hidden="true" '
        f'style="--db-x:{x}%;--db-y:{y}%;"></span>'
    )


def render_horizontal_connector(component: str, x_positions: list) -> tuple[str, list]:
    """Render horizontal arrow shafts and side arrowheads."""
    x1, x2 = x_positions[0], x_positions[1]
    animated_class = ' class="db-component__flow-line"' if component.startswith("animated-") else ""
    lines = f'    <line{animated_class} x1="{x1 + 13}" y1="50" x2="{x2 - 13}" y2="50" />'
    heads = []
    if "right-arrow" in component or "two-way" in component:
        heads.append(render_horizontal_arrowhead(x2 - 13, 50, "right"))
    if "left-arrow" in component or "two-way" in component:
        heads.append(render_horizontal_arrowhead(x1 + 13, 50, "left"))
    return lines, heads


def render_horizontal_arrowhead(x: float, y: float, direction: str) -> str:
    """Render a CSS horizontal arrowhead."""
    return (
        '<span class="db-component__arrowhead-horizontal '
        f'db-component__arrowhead-horizontal--{escape(direction, quote=True)}" aria-hidden="true" '
        f'style="--db-x:{x}%;--db-y:{y}%;"></span>'
    )


def css_token(value: str) -> str:
    """Return a conservative CSS class token."""
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value.strip().lower())[:40]


def render_top_connector_lines(x_positions: list) -> tuple[str, list]:
    """Render the shared top rail, incoming stem, and node edge arrows."""
    start = x_positions[0]
    end = x_positions[-1]
    arrow_heads = [render_component_arrowhead(x, 39) for x in x_positions]
    branch_lines = "\n".join(
        render_component_arrow_line(x, 20, 39)
        for x in x_positions
    )
    return (
        f'    <line x1="50" y1="0" x2="50" y2="20" />\n'
        f'    <line x1="{start}" y1="20" x2="{end}" y2="20" />\n'
        f"{branch_lines}"
    ), arrow_heads


def render_bottom_connector_lines(x_positions: list) -> tuple[str, list]:
    """Render node-to-bottom-rail lines and the centered bottom arrow."""
    start = x_positions[0]
    end = x_positions[-1]
    branch_lines = "\n".join(
        f'    <line x1="{x}" y1="61" x2="{x}" y2="76" />'
        for x in x_positions
    )
    return (
        f"{branch_lines}\n"
        f'    <line x1="{start}" y1="76" x2="{end}" y2="76" />\n'
        f"{render_component_arrow_line(50, 76, 94)}"
    ), [render_component_arrowhead(50, 94)]


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
      <marker id="db-arrow" viewBox="0 0 12 9" refX="6" refY="0" markerWidth="12" markerHeight="9" orient="0">
        <path d="M0,0 L12,0 L6,9 Z" />
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


def render_diagram(diagram: dict, components: dict, diagram_id: int) -> str:
    """Render one diagram block by dispatching on its type."""
    title = diagram.get("title")
    heading = f'<h2 class="db-diagram__heading">{escape(str(title))}</h2>' if title else ""

    if diagram["type"] == "flow":
        body = render_flow(diagram, components)
    elif diagram["type"] == "tree":
        body = render_tree(diagram, components)
    elif diagram["type"] == "component":
        body = render_architecture_component(diagram, diagram_id)
    elif diagram["type"] == "component_stack":
        body = render_component_stack(diagram, diagram_id)
    elif diagram["type"] == "component_gallery":
        body = render_component_gallery(diagram_id)
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

    diagram_html = "\n".join(
        render_diagram(diagram, components, index + 1)
        for index, diagram in enumerate(payload["diagrams"])
    )
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
