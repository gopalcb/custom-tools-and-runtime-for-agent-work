# Design Rules

These rules exist to keep AI-generated UI inside the existing Layout Builder theme instead of drifting into random styles.

## Read Order
1. Read `root.yaml` first.
2. Read the component YAML files that match the UI you are generating.
3. If a component is missing, compose it from the closest existing files before inventing anything new.
4. Only read `layout-builder/theme/theme-library.html` or `layout-builder/theme/theme-ref.html` to verify details, not to override the YAML rules.

## Non-Negotiable Rules
- Use the token values in `root.yaml` as the source of truth.
- Keep rectangular corners at `4px`.
- Keep the warm neutral palette and muted green accent.
- Use borders for separation before adding stronger shadows.
- Keep type restrained and compact.
- Prefer simple, structured layouts over decorative layouts.
- When a component file exists, match it instead of improvising.

## Do Not Invent
- New accent colors.
- New border radius values for rectangular controls.
- New shadows unless the user explicitly asks for a new elevation pattern.
- Random gradients, glassmorphism, neon effects, or dark-mode reinterpretations.
- Pill buttons or pill tags unless a token file explicitly allows them.
- Oversized hero sections for admin or utility screens unless the user asks for marketing treatment.

## Global Visual Direction
- Mood: quiet, editorial, neutral, utility-first.
- Surfaces: soft warm panels on a light neutral background.
- Separation: thin borders, subtle contrast shifts, light shadow only where needed.
- Type: compact sizes, uppercase micro-labels, dense but readable spacing.
- Accent usage: muted green for primary action, focus, selected states, and success-like emphasis.

## Layout Rules
- Page body should use the `body.yaml` section shell and spacing rules.
- Prefer 3-column sample grids on desktop and 1-column on mobile.
- Keep section headers compact with small uppercase kickers and one clear title.
- Leave visible breathing room between panels. Do not compress everything into one dense slab.

## Control Rules
- Buttons must follow `button.yaml`.
- Text inputs and textareas must follow `textbox.yaml`.
- Dropdowns must follow `dropdown.yaml`.
- Checkboxes must follow `checkbox.yaml`.
- Form groups must follow `formgroup.yaml`.
- Tables must follow `table.yaml`.

## Dropdown Rule
- If exact alignment of the selected-state checkmark matters, use the custom dropdown pattern from `dropdown.yaml`.
- Do not depend on browser-native option menu rendering when the UI must be visually controlled.
- Keep a fixed-width checkmark slot so option labels align even when only one row is selected.

## Header And Footer Rules
- Keep headers compact and utility-oriented.
- Keep footers optional and low emphasis.
- Do not turn header or footer into marketing banners unless the user explicitly asks for that.

## Missing Component Procedure
If a needed component does not have a YAML file:
1. Reuse `root.yaml` tokens.
2. Borrow spacing and shell rules from `body.yaml` or `card.yaml`.
3. Borrow interaction rules from the closest control file.
4. Document the assumption in code comments or a short note.
5. Do not create a new visual language.

## Agent Output Expectations
- Generated UI should look like it belongs to the same product as `theme-library.html`.
- A reviewer should be able to point to a token file and explain every major visual choice.
- If a style choice cannot be traced back to these files or an explicit user request, it is probably wrong.
