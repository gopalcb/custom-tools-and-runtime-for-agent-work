# Codex Agent + Skill Architecture Best Practices

## Recommendation

Use a **hybrid architecture**:

> **Agents define responsibility and execution boundaries. Skills define reusable knowledge and procedures. Codex loads the skills needed by the active agent.**

Do not create a separate agent for every small capability, and do not put every capability into one large general-purpose agent.

---

## Core Model

| Concept | Responsibility | Example |
|---|---|---|
| `AGENTS.md` | Repository-wide operating guidance | architecture rules, testing expectations, documentation map |
| Agent | Owns a job or responsibility | `ui-architect`, `backend-developer` |
| Skill | Reusable capability or methodology | `ui-design-rules`, `rest-api-design` |
| Tool | Something the agent can operate | Selenium, shell, browser, web search |
| Workflow | Defines ordering and dependencies | architect → prototype → implement → validate |
| Subagent | Temporary bounded worker | explorer, tester, reviewer |

---

## Decision Rule: Agent vs Skill

Use this rule:

> **Does it perform a job, or teach how to perform a job?**

If it **owns a responsibility**, make it an agent.

Examples:

- `ui-architect`
- `api-architect`
- `ux-designer`
- `frontend-developer`
- `backend-developer`
- `security-reviewer`
- `planner`

If it **teaches a reusable capability**, make it a skill.

Examples:

- `ui-design-rules`
- `angular-development`
- `rest-api-design`
- `api-contract-design`
- `selenium-browser-navigation`
- `python-development`
- `testing`
- `security-review-methodology`

---

## Recommended Agents

Keep the number of permanent agents relatively small.

### `ui-architect`

Responsibilities:

- Convert requirements into information architecture.
- Determine pages, navigation, menus, tables, cards, forms, and content hierarchy.
- Decide where functionality should live in the UI.
- Produce a clean UI architecture before implementation.

Typical skills:

- `ui-design-rules`
- `information-architecture`
- `ui-research`

---

### `api-architect`

Responsibilities:

- Design REST APIs.
- Define required endpoints.
- Define request/response contracts.
- Define validation and business logic boundaries.
- Identify shared APIs and reusable backend capabilities.

Typical skills:

- `rest-api-design`
- `api-contract-design`
- `backend-architecture`

---

### `ux-designer`

Responsibilities:

- Follow approved UI architecture.
- Build end-to-end HTML/CSS prototypes.
- Cover all pages and important interaction states.
- Validate usability and visual consistency.

Typical skills:

- `ui-design-rules`
- `html-prototyping`
- `browser-validation`

---

### `frontend-developer`

Responsibilities:

- Build the Angular application.
- Integrate backend APIs.
- Reuse shared components.
- Implement routing, forms, state, validation, and UI behavior.
- Validate the application in a browser.

Typical skills:

- `angular-development`
- `typescript-development`
- `api-integration`
- `ui-design-rules`
- `browser-validation`
- `testing`

---

### `backend-developer`

Responsibilities:

- Build the REST API.
- Implement business logic.
- Implement validation.
- Integrate persistence and external services.
- Make APIs available for frontend consumption.
- Add tests.

Typical skills:

- `backend-development`
- `rest-api-design`
- `api-validation`
- `database-development`
- `testing`

---

## Shared Skills

Skills should be reusable by multiple agents.

Example:

```text
ui-design-rules
       │
       ├── ui-architect
       ├── ux-designer
       └── frontend-developer
```

Do not copy the same UI rules into multiple agent instruction files.

Maintain one source of truth and let different agents consume it.

---

## Recommended Resolution Flow

Your resolver should choose the **agent**, not manually inject every possible skill into the prompt.

Example:

```yaml
agent: frontend-developer

available_skills:
  - angular-development
  - ui-design-rules
  - api-integration
  - browser-validation
  - testing

context:
  - ARCHITECTURE.md
  - code-map.yaml

workflow:
  - inspect
  - implement
  - validate
```

Then the active Codex agent loads relevant skills as needed.

Conceptually:

```text
USER PROMPT (label-upper)
    │ (down-arrow)
    ▼
Agent Resolver  (label-normal)
    │ (down-arrow-with-right-branches)
    ├── determine owner
    │
    ▼
frontend-developer  (label-lower)
    │
    ▼
CODEX SKILL SELECTION (label-upper)
    │ (down-arrow-with-right-branches)
    ├── angular-development
    ├── api-integration
    ├── ui-design-rules
    └── browser-validation
```

This keeps the resolver simple.

The resolver answers:

> **Who should handle this?**

The active agent and Codex skill mechanism answer:

> **What knowledge is needed to complete it?**

---

## Permanent Agents vs Temporary Subagents

Do not create permanent agents for every narrow task.

Avoid:

```text
angular-agent
css-agent
html-agent
typescript-agent
selenium-agent
rest-agent
database-agent
unit-test-agent
```

Prefer:

```text
frontend-developer
    ├── angular-development skill
    ├── typescript-development skill
    ├── ui-design-rules skill
    ├── browser-validation skill
    └── testing skill

backend-developer
    ├── rest-api-design skill
    ├── database-development skill
    ├── api-validation skill
    └── testing skill
```

The number of skills can grow much faster than the number of agents.

A healthy long-term structure may look like:

```text
6-10 permanent agents
30-100+ reusable skills
temporary subagents created when needed
```

---

## When a Separate Agent Is Justified

Create a specialized agent when one or more of these are true:

- It owns a clearly separate responsibility.
- It needs separate context.
- It produces a distinct deliverable.
- It needs different tools or permissions.
- It should use a different model or reasoning level.
- It can run independently or in parallel.
- Its work would create too much noise in the main agent context.

Examples:

```text
ui-architect
api-architect
frontend-developer
backend-developer
security-reviewer
planner
```

---

## When Something Should Stay a Skill

Prefer a skill when:

- Multiple agents need the same knowledge.
- The capability is procedural.
- It contains rules, patterns, conventions, or examples.
- It does not need its own execution context.
- It does not own a separate deliverable.
- Creating a separate agent would add orchestration overhead.

Examples:

```text
ui-design-rules
angular-development
python-development
rest-api-design
testing
selenium-navigation
security-review-rules
```

---

## Temporary Subagents

Use temporary Codex subagents for bounded parallel work.

Example:

```text
frontend-developer
        │
        ├── explorer
        │     investigate existing routing
        │
        ├── explorer
        │     inspect reusable UI components
        │
        ├── tester
        │     run browser/test validation
        │
        └── reviewer
              inspect final changes
```

These workers do not need permanent folders or identities unless the responsibility becomes recurring and substantial.

Good temporary subagent tasks:

- repository exploration
- code search
- test execution
- browser inspection
- log analysis
- architecture review
- implementation review
- independent research

Be more cautious with multiple agents modifying the same files in parallel because merge conflicts and duplicated implementation can occur.

---

## Three-Level Architecture

```text
LEVEL 1 — ROLE / RESPONSIBILITY

ui-architect
api-architect
frontend-developer
backend-developer
ux-designer

            │
            ▼

LEVEL 2 — REUSABLE CAPABILITY

ui-design-rules
angular-development
rest-api-design
testing
browser-navigation
python-development

            │
            ▼

LEVEL 3 — TEMPORARY WORKER

explorer
researcher
tester
reviewer
debugger
```

This keeps specialization without creating agent sprawl.

---

## Recommended Repository Structure

```text
monorepo/
│
├── AGENTS.md
├── ARCHITECTURE.md
├── code-map.yaml
│
├── .agents/
│   └── skills/
│       ├── ui-design-rules/
│       │   └── SKILL.md
│       ├── angular-development/
│       │   └── SKILL.md
│       ├── rest-api-design/
│       │   └── SKILL.md
│       ├── browser-navigation/
│       │   └── SKILL.md
│       ├── python-development/
│       │   └── SKILL.md
│       └── testing/
│           └── SKILL.md
│
├── .codex/
│   └── agents/
│       ├── ui-architect.toml
│       ├── api-architect.toml
│       ├── ux-designer.toml
│       ├── frontend-developer.toml
│       └── backend-developer.toml
│
├── agents/
│   ├── resolver/
│   ├── workflow-orchestrator/
│   └── runtime/
│
├── docs/
│   ├── architecture/
│   ├── design/
│   ├── api/
│   └── decisions/
│
└── application-code/
```

---

## Keep `AGENTS.md` Small

Do not turn `AGENTS.md` into a massive instruction manual.

It should mainly tell Codex:

- how the repository is organized
- which architecture files are authoritative
- where skills live
- where agent definitions live
- how testing should be performed
- which files must be kept synchronized

Example:

```markdown
# Repository Agent Guidance

Before making significant changes:

1. Read `ARCHITECTURE.md`.
2. Read `code-map.yaml`.
3. Load the skills relevant to the task.
4. Reuse existing functions/components before creating new ones.
5. Update `ARCHITECTURE.md` when architecture changes.
6. Update `code-map.yaml` when files/functions are added, removed, or renamed.
7. Run appropriate tests before completion.
```

Detailed knowledge should live in dedicated skills or documentation.

---

## Repository Knowledge Should Be the Source of Truth

Keep important project knowledge in repository files rather than embedding it inside individual agents.

Recommended hierarchy:

```text
AGENTS.md
    │
    ▼
ARCHITECTURE.md
    │
    ▼
code-map.yaml
    │
    ▼
specialized documentation
    │
    ▼
skills
    │
    ▼
source code
```

This allows Codex to progressively discover context instead of receiving a huge prompt on every run.

---

## Avoid Duplicate Knowledge

Bad:

```text
ui-architect.md
    contains UI rules

frontend-developer.md
    contains duplicate UI rules

ux-designer.md
    contains another copy of UI rules
```

Better:

```text
ui-design-rules/SKILL.md
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
 UI Architect UX  Frontend
```

The agent file should describe:

- responsibility
- expected input
- expected output
- boundaries
- preferred tools
- relevant skill categories

The skill should describe:

- methodology
- rules
- patterns
- examples
- validation criteria

---

## Suggested Resolver Responsibility

The resolver should remain intentionally small.

It should determine:

```yaml
agent:
skills_available:
workflow:
context:
tools:
```

It should not attempt to perform the specialist's reasoning.

Example:

```yaml
resolution:
  agent: ui-architect

  skills_available:
    - ui-design-rules
    - information-architecture
    - ui-research

  context:
    - ARCHITECTURE.md
    - docs/design/

  workflow:
    - inspect-existing-ui
    - derive-information-architecture
    - design-page-structure
    - review

  tools:
    - repository-search
    - browser
    - web-search-if-needed
```

---

## Workflow Example

For a new application feature:

```text
User requirement
      │
      ▼
Planner / Orchestrator
      │
      ▼
UI Architect
      │
      ├── UI design rules skill
      └── produces UI architecture
      │
      ▼
API Architect
      │
      ├── REST design skill
      └── produces API contract
      │
      ├─────────────────┐
      ▼                 ▼
UX Designer      Backend Developer
      │                 │
      ▼                 ▼
HTML prototype      Working API
      │                 │
      └────────┬────────┘
               ▼
       Frontend Developer
               │
               ▼
       Angular integration
               │
               ▼
        Browser validation
               │
               ▼
             Review
```

Parallel work should only happen when dependencies allow it.

---

## Suggested Guiding Principles

### 1. Agents represent ownership

An agent should have a clear sentence describing what it owns.

Example:

> `api-architect` owns the API contract and backend service boundaries.

If the responsibility cannot be described clearly, it may not need to be a separate agent.

### 2. Skills represent reusable expertise

A skill should be usable by more than one workflow or agent whenever possible.

### 3. Prefer progressive context loading

Do not preload every skill and documentation file into every Codex request.

Load what is relevant to the current task.

### 4. Avoid orchestration for trivial tasks

A one-file bug fix does not need five agents.

The resolver can send it directly to the appropriate developer agent.

### 5. Use parallelism for independent work

Good:

```text
explore frontend
explore backend
inspect tests
```

Potentially problematic:

```text
three agents editing the same Angular component simultaneously
```

### 6. Keep permanent agent count low

Create a new permanent agent only when there is a durable responsibility boundary.

### 7. Keep project knowledge outside prompts

Architecture, conventions, component maps, API rules, and history should be inspectable repository artifacts.

### 8. Enforce important rules mechanically where possible

Do not depend only on prompts for rules that can be checked automatically.

Examples:

- lint rules
- architecture checks
- schema validation
- tests
- dependency-boundary validation
- code-map consistency checks

---

## Recommended Architecture for This Monorepo

```text
                            USER
                              │
                              ▼
                       Agent Resolver
                              │
                    resolve responsibility
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
      UI Architect       API Architect       Developers
           │                  │              │        │
           └──────────────── Skills ─────────┘        │
                              │                       │
                       progressive loading           │
                              │                       │
              ┌───────────────┼──────────────┐        │
              ▼               ▼              ▼        ▼
         UI Design        REST/API        Angular   Testing
           Rules           Design
                              │
                              ▼
                      Temporary Subagents
                 explorer / tester / reviewer
```

---

## Final Recommendation

Build the system around this separation:

```text
Agent      = Who owns the work
Skill      = How the work should be done
Tool       = What can be operated
Workflow   = In what order work happens
Subagent   = Temporary additional worker
Context    = What repository knowledge is required
```

For the current monorepo:

```text
Permanent agents:
- ui-architect
- api-architect
- ux-designer
- frontend-developer
- backend-developer

Reusable skills:
- ui-design-rules
- information-architecture
- angular-development
- rest-api-design
- api-contract-design
- python-development
- browser-navigation
- testing
- security-review-rules
```

Allow Codex to load relevant skill contents on demand rather than injecting all skill documentation into every agent prompt.

Use temporary subagents for exploration, research, testing, debugging, and review.

This gives the system specialization while keeping context size, duplication, orchestration complexity, and long-term maintenance under control.

---

## References

Current Codex documentation and OpenAI engineering guidance supporting this model:

- Codex Skills: https://developers.openai.com/codex/build-skills
- Codex custom agents and subagents: https://developers.openai.com/codex/agent-configuration/subagents
- OpenAI harness engineering / repository knowledge practices: https://openai.com/index/harness-engineering/
- Codex overview and skill-oriented workflows: https://openai.com/index/introducing-the-codex-app/
