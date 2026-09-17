# Compact Diagram Builder

Render YAML diagrams to transparent-background HTML:

```bash
python my-system-libs/agent-custom-tools/diagram-builder/main.py input.yaml output.html --css-href assets/styles.css
```

Additional compact components include `square-with-text`,
`square-with-icon-detail`, `horizontal-right-arrow`, `horizontal-left-arrow`,
and `horizontal-two-way-arrow`. Node mappings can use `icon`, `detail`, `size`,
`color`, and `style`.

## Generate New Component Sample

```bash
python diagram_builder.py sample-new-components.yaml sample-new-components.html --components libs/components.yaml --css-href assets/styles.css
python test.py
```

The generated sample should include right, left, bidirectional, square, icon,
detail, size, color, and style variants. `assets-view.html` is an interactive
catalog for the full component set, and the architecture combination pages show
how an agent can combine those pieces into complete system diagrams.
