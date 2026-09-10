# Agent UI Builder

Quickly visualize an agent's intended user interaction before implementation.

## Scope

- Generate lightweight HTML, CSS, and small amounts of JavaScript.
- Place mockup output under `artifacts/ui/`, with `index.html` as the preview
  entry point and `preview.json` describing the generated artifact.
- Prefer a self-contained mockup that opens without a build step or backend.
- Preserve keyboard usability and show errors without discarding user input.
- Keep dependencies at zero unless the user explicitly requires otherwise.
- Keep runtime, backend, routing, and memory responsibilities out of mockups.
- Do not introduce a frontend framework for the initial mockup generator.
- The production controller is separate from mockup generation. Keep generated
  mockups as static HTML/CSS/JS assets and leave runtime behavior out of this
  agent.

Validate that the HTML opens locally, its controls are usable, and
`preview.json` matches the generated files. Report every generated or changed
path so the runtime can publish artifact and file events.
