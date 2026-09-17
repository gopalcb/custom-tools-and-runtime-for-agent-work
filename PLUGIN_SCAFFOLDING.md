# Plugin Scaffolding Instructions

Use this guide when an agent needs to turn `my-system-libs/` into a Codex
plugin.

The goal is to package the compact runtime and tools without making them
mysterious. Preserve the direct-folder shape. A plugin should make the tools
easier to install and invoke, not harder to inspect.

## Plugin Intent

Create a plugin named `custom-agent-tools-and-runtime`.

The plugin should provide:

- a skill that teaches agents how to use the compact runtime;
- access to the diagram builder for consistent YAML-to-HTML diagrams;
- access to MQ message examples and topic contracts;
- optional CLI wrappers for runtime commands;
- documentation that keeps state, workflows, and generated artifacts visible.

## Recommended Layout

```text
custom-agent-tools-and-runtime/
  .codex-plugin/
    plugin.json
  skills/
    custom-agent-runtime/
      SKILL.md
  tools/
    my-system-libs/
      runtime.py
      runtime_support.py
      project.toml
      requirements.txt
      workflow/
      mq_server/
      memory-server/
      agent-custom-tools/
      articles/
  README.md
```

Keep source paths stable when possible. Agents should still be able to inspect
`runtime.py`, `mq_server/handler.py`, workflow YAML, and diagram-builder files
directly.

## Manifest Draft

Start with a simple plugin manifest:

```json
{
  "schema_version": "v1",
  "name": "custom-agent-tools-and-runtime",
  "version": "0.1.0",
  "description": "Compact custom-agent runtime, MQ messaging, memory, and diagram tools.",
  "skills": [
    {
      "name": "custom-agent-runtime",
      "path": "skills/custom-agent-runtime/SKILL.md"
    }
  ]
}
```

Adjust field names only if the active Codex plugin schema requires it.

## Skill Draft

Create `skills/custom-agent-runtime/SKILL.md` with instructions like:

````markdown
---
name: custom-agent-runtime
description: Use the compact custom-agent runtime, MQ topic handlers, memory server, and diagram builder.
---

# Custom Agent Runtime

Use this skill when a task asks for compact agent runtime behavior, MQ message
flows, durable agent-to-agent messaging, memory records, or consistent
YAML-to-HTML diagrams.

Start by reading `tools/my-system-libs/README.md`, then inspect the specific
owner file:

- runtime facade: `tools/my-system-libs/runtime.py`
- MQ topics: `tools/my-system-libs/mq_server/handler.py`
- workflow YAML: `tools/my-system-libs/workflow/yamls/`
- diagram builder: `tools/my-system-libs/agent-custom-tools/diagram-builder/`

Prefer direct commands:

```bash
python tools/my-system-libs/test.py
python tools/my-system-libs/runtime.py resolve-workflow --workflow analysis
python tools/my-system-libs/runtime.py run --workflow analysis --prompt "smoke test"
```

For diagrams, author YAML first, then render HTML with the diagram builder.
Keep generated HTML beside the YAML when the artifact is part of docs.
````

## Agent Tasks

When creating the plugin, the agent should:

1. Copy `my-system-libs/` into `tools/my-system-libs/`.
2. Add `.codex-plugin/plugin.json`.
3. Add `skills/custom-agent-runtime/SKILL.md`.
4. Keep `README.md`, `ARCHITECTURE.md`, and `code-map.yaml` with the copied
   tools.
5. Run the smoke tests from the plugin root.
6. Verify that generated diagram HTML still resolves its relative CSS link.
7. Avoid adding a second runtime abstraction unless a real plugin API requires
   it.

## Validation

Run:

```bash
python tools/my-system-libs/test.py
python tools/my-system-libs/mq_server/test.py
python tools/my-system-libs/workflow/test.py
python tools/my-system-libs/agent-custom-tools/diagram-builder/test.py
```

If Python dependencies are not available, document the missing dependency and
the install command from `tools/my-system-libs/requirements.txt`.

## Boundaries

Do not move durable state into the plugin folder by default. The runtime should
continue writing state under the selected project root's `.agent-state/`.

Do not replace the direct YAML workflow, MQ handler, or diagram-builder files
with generated wrappers. The plugin should expose the existing system, not bury
it.

Do not claim live AWS page-view logging works from Markdown unless the logging
stack has been deployed with GET `/agent/logging/visit` support.
