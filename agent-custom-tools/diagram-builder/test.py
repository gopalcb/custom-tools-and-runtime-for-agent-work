"""
Smoke tests for the compact diagram builder.

The tests verify both the copied component families and the new square,
horizontal, and bidirectional connector components.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from diagram_builder import load_component_catalog, render_document, validate_document


ROOT = Path(__file__).resolve().parent


def test_new_components_render() -> None:
    """Verify the newly requested component variants render into HTML."""
    components = load_component_catalog(ROOT / "libs" / "components.yaml")
    payload = yaml.safe_load((ROOT / "sample-new-components.yaml").read_text(encoding="utf-8"))
    validated = validate_document(payload, components)
    html = render_document(validated, components, "assets/styles.css")
    assert "db-component--horizontal-right-arrow" in html
    assert "db-component--horizontal-left-arrow" in html
    assert "db-component--horizontal-two-way-arrow" in html
    assert "animated-horizontal" not in html
    assert "db-component__node--square" in html
    assert "db-component__icon" in html


def main() -> int:
    """Run diagram-builder smoke tests."""
    test_new_components_render()
    print("diagram-builder tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
