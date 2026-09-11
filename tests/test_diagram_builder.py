from pathlib import Path
import sys

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_BUILDER_ROOT = PROJECT_ROOT / "agent-tools" / "diagram-builder"
sys.path.append(str(DIAGRAM_BUILDER_ROOT))

from diagram_builder import load_component_catalog, render_document, validate_document


def test_sample_diagram_renders_expected_components() -> None:
    """Verify the sample YAML renders all supported diagram families."""
    components = load_component_catalog(DIAGRAM_BUILDER_ROOT / "assets" / "components.yaml")
    payload = yaml.safe_load((DIAGRAM_BUILDER_ROOT / "sample.yaml").read_text(encoding="utf-8"))
    validated = validate_document(payload, components)

    html = render_document(validated, components, "assets/styles.css")

    assert "USER PROMPT" in html
    assert "db-tree__root" in html
    assert "EventHub" in html
    assert "memory candidates" in html


def test_unknown_flow_component_fails_validation() -> None:
    """Verify flow diagrams can only use catalog-backed components."""
    components = load_component_catalog(DIAGRAM_BUILDER_ROOT / "assets" / "components.yaml")
    payload = {
        "diagrams": [
            {
                "type": "flow",
                "steps": [{"component": "mystery-box", "text": "Nope"}],
            }
        ]
    }

    with pytest.raises(ValueError, match="unknown flow component"):
        validate_document(payload, components)


def test_invalid_tree_child_fails_validation() -> None:
    """Verify malformed tree children fail before HTML rendering."""
    components = load_component_catalog(DIAGRAM_BUILDER_ROOT / "assets" / "components.yaml")
    payload = {
        "diagrams": [
            {
                "type": "tree",
                "root": {"name": "monorepo/", "children": ["AGENTS.md"]},
            }
        ]
    }

    with pytest.raises(ValueError, match="tree child must be a mapping"):
        validate_document(payload, components)
