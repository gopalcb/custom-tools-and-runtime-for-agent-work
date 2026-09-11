# Reuse Policy

## Search Order

1. `application-systems/component-libs/components/core` for system
   primitives.
2. `application-systems/component-libs/components` for built-in page
   components.
3. `application-systems/layout-builder/src/app/components` for composed app
   screens.
4. `application-systems/layout-builder/src/app/services` for frontend state and
   integration behavior.
5. `application-systems/data-api-services/layout-builder-backend/src` for API
   ownership and persistence behavior.

## Rules

- Do not create a new function if an existing one can be generalized safely.
- Do not create parallel services for the same data source or ownership
  boundary.
- Do not create a new component variant if inputs or composition cover the need.
- Avoid catch-all folders or services named `utils`, `helpers`, or `common`.
- When adding a reusable symbol, mention why reuse was not sufficient in the
  change summary or a short nearby note.
