---
name: ui-design-rules
description: Core UI organization and design rules. Use when planning, designing, reviewing, or implementing application interfaces, navigation, forms, tables, cards, dashboards, workflows, or page layouts.
---

# UI Design Rules

Apply these rules to all application UI work.

## Rules

- Start from the user's primary goal; organize the page around the next action they need to take.
- Establish clear hierarchy: primary content/actions first, secondary controls quieter, rare actions hidden behind menus or contextual controls.
- Group related information and actions together. Do not scatter one workflow across unrelated areas.
- Keep navigation predictable. Use stable locations for primary navigation and contextual navigation.
- Prefer simple page structures over deeply nested panels, cards, tabs, and modals.
- Use cards only when content forms a meaningful independent group; do not wrap everything in cards.
- Use tables for structured comparable data. Keep primary columns visible and move rare row actions to contextual menus when appropriate.
- Keep forms ordered by user workflow. Group related fields and avoid asking for information before it is needed.
- Use progressive disclosure for advanced settings and uncommon options.
- Avoid duplicated actions, repeated information, decorative controls, and non-actionable metrics.
- Loading, empty, error, disabled, success, and partial states are part of the UI design.
- Keep terminology, action placement, spacing, component behavior, and interaction patterns consistent across pages.
- Prefer reuse of an existing pattern/component before introducing a new one.
- Do not create abstractions or components solely to reduce line count.
- Design responsive behavior intentionally; preserve information priority on smaller screens.
- Preserve accessibility: semantic elements, labels, keyboard access, visible focus, readable text, and sufficient contrast.

## Final Check

Before finalizing, remove anything that does not help the user understand state, make a decision, or complete an action.
