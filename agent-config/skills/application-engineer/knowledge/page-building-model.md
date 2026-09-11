# Page Building Model

This note migrates the useful product relationship from the old
`agentic-web-dev` project into the current `application-systems` structure.

## Current Relationship

- A project owns pages.
- Pages are composed in `application-systems/layout-builder`.
- Pages should use one active built-in theme and approved built-in components.
- Built-in theme and component assets live in
  `application-systems/component-libs`.
- `application-systems/component-libs/library.json` declares the default
  library, default landing layout, component metadata, and Angular source
  references.
- Each built-in component is a standalone Angular component under
  `application-systems/component-libs/components/<component-id>`, with
  `<component-id>.component.ts`, template, and style files. The library also
  exposes `application-systems/component-libs/public-api.ts` for direct imports.
- Runtime and persistence concerns live in
  `application-systems/data-api-services/layout-builder-backend`.
- The backend hydrates the default library from repo files and exposes it at
  `GET /api/component-libraries/default`.

## Simplified Authoring Scope

For now, the layout builder should stay focused on project/page composition.
Theme, template, and component creation remain internal or direct-route flows,
not primary header destinations.

The header should emphasize:

- Build Page
- Pages
- Projects
- Analytics
- Agentic Workflow

The relationship to preserve is that built-in components and the active theme
are system-provided ingredients for building project pages. Users compose pages
from those ingredients rather than designing a new component library or theme
from the main navigation.

## Composition Mechanics

- Pages own rectangles.
- Rectangles can reference a built-in component with `linkedComponentId`.
- Rectangles carry instance-level `componentProps` and `fitBehavior`.
- Canvas and preview rendering resolve `linkedComponentId` against the component
  catalog, then render by component `type`.
- Theme records from `/api/themes` are design-rule and color snapshots. The
  initial page-building bootstrap comes from the default component library and
  its `defaultLayout`.

## Agent Guidance

- When adding page-building behavior, search the current component seeds,
  `component-libs/library.json`, and backend API contracts first.
- When a page needs a control or common layout element, prefer a system core
  primitive or default Angular library component.
- Do not introduce a new visual language to satisfy a page-building request.
- Keep routes for internal authoring screens intact unless explicitly asked to
  remove the feature surface.
