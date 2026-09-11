---
name: application-engineer
description: Build and maintain the application-systems projects: layout-builder, component-libs, and data-api-services, using curated themes/components and the Layout Builder product model.
---

# Application Engineer

Use this skill for work in `application-systems/layout-builder`,
`application-systems/component-libs`, and `application-systems/data-api-services`.

## Project Model

- `layout-builder` is the Angular 20 standalone application for composing and
  previewing project pages.
- `component-libs` is the built-in component library. It contains approved
  callable Angular components and metadata that pages can use.
- `data-api-services/layout-builder-backend` is the unified API for persisted
  layout state, projects, pages, components, themes, analytics, notifications,
  and agent operations.
- `data-api-services/agentic-component-builder` is legacy standalone generation
  infrastructure unless a task explicitly targets it.

## Required Workflow

1. Read this file and the relevant files in `knowledge/`.
2. For UI work, read `design-tokens/design-rules.md` and
   `design-tokens/root.yaml`.
3. Read only component token files that match the control or surface you are
   touching.
4. Check `application-systems/layout-builder/docs/map-index.md` when it can
   reduce source reads.
5. Search existing components, services, and library metadata before adding new
   code.
6. Reuse or extend existing symbols before creating parallel implementations.
7. Refresh generated knowledge after meaningful `layout-builder` source changes
   with `npm run knowledge:refresh` from `application-systems/layout-builder`.

## UI Rules

- Keep generated and hand-authored UI inside the active built-in theme.
- Use standalone Angular components, `inject()` for dependency access, and
  colocated template/style files.
- Keep reusable system primitives under
  `application-systems/component-libs/components/core`.
- Keep composed layout-builder screens under
  `application-systems/layout-builder/src/app/components`.
- Prefer the built-in `app-button`, `app-dropdown`, `app-input`,
  `app-checkbox`, `app-radio`, `app-modal`, `app-alert`, and `app-header`
  primitives before creating one-off controls.
- Use the default component library for page composition. Do not surface
  component, template, or theme building as primary header navigation unless the
  product scope changes.

## Quality Gates

- Human and agent paths must produce compatible page/component artifacts.
- Backend contracts must validate inputs instead of trusting generated payloads.
- Agent jobs must expose status, errors, retry semantics, and traceable outputs.
- Run build/typecheck/code-map checks for the project slice you change.
