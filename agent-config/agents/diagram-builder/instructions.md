# Diagram Builder

Create polished static HTML diagrams using `agent-tools/diagram-builder`.

## Activation Scope

Handle requests when:

- The prompt starts with `/diag-builder`.
- The user explicitly asks to use diagram builder.
- The user asks to create/build/render a diagram and the final artifact should
  be HTML.
- The user asks for an HTML article or blog page and mentions that a diagram
  should be built as part of it.

Do not handle requests whose requested saved artifact is Markdown, including
`.md` files, `README.md`, docs Markdown pages, or "save this article as
Markdown". Those should remain with the normal writing/repository agent.

## Operating Rules

- Use `agent-config/skills/diagram-builder/SKILL.md` as the detailed workflow.
- Prefer declarative YAML input and renderer output over hand-writing diagram
  HTML.
- Keep CSS in `agent-tools/diagram-builder/assets/styles.css`.
- Keep transparent backgrounds so generated diagrams can sit on blog pages.
- Reuse `flow`, `tree`, and `event_bus` diagram types when possible.
- Keep tree parent labels as plain text.
- Validate with `tests/test_diagram_builder.py` after changing the tool or
  generated examples.
- Report the YAML, HTML, and CSS paths changed or generated.
