# Codex Agent Console — Initial Python/TUI Implementation Plan

> **Status:** Initial implementation plan  
> **UI source of truth:** the approved `Pasted code.html` supplied with this task  
> **Implementation scope:** local Python TUI with a hardcoded/mock workflow and simulated background activity  
> **Out of scope for this phase:** real Codex app-server integration, real model execution, real token accounting, real file writes, real permission handling, real subagent execution
>
> This document is intended to be given directly to a Codex worker/coordinator agent. The coordinator must use multiple parallel worker agents where tasks are safely separable, merge their work carefully, run the full validation suite, and perform a final **nothing-missed audit** against this document and the approved HTML.

---

# 1. Primary Objective

Build a local, lightweight Python terminal application that faithfully reproduces the approved Codex Agent Console UI and behavior using:

- Python 3.11+
- Textual for the application shell, layout, widgets, event loop, keyboard input, scrolling, focus, and terminal resizing
- Rich for styled logs, syntax-highlighted code, text formatting, and renderables where useful
- asyncio for mock workflow/background-task concurrency
- Python standard library for models/state wherever practical

The initial version must be fully local and deterministic.

No Codex server or API integration is required yet.

The purpose of Phase 1 is to validate:

1. terminal layout;
2. workflow state transitions;
3. animated in-progress states;
4. completed/failed/retry states;
5. parallel background tasks;
6. log streaming;
7. inline code rendering;
8. prompt interaction;
9. responsive terminal resizing;
10. architecture readiness for later Codex app-server integration.

---

# 2. Design Contract — Do Not Drift

The attached HTML is the visual source of truth for this phase.

Workers must not redesign the interface.

The approved layout consists of five major vertical regions:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Title Bar                                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Agent / Model / Session / Active                                            │
├────────────────┬─────────────────────────────────┬──────────────────────────┤
│ Workflow       │ Current Activity / Logs / Code  │ Background Tasks         │
│                │                                 │                          │
│                │                                 │                          │
├────────────────┴─────────────────────────────────┴──────────────────────────┤
│ Codex-style Prompt Input                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Footer                                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

The center section in the approved HTML is intentionally simple:

- one current-activity header;
- one scrolling content/log area;
- generated code appears inline within that log/content area;
- no Logs/Code/Diff/Preview tab system in this phase.

**Do not reintroduce the earlier tabbed center design.**

---

# 3. Approved UI Details

## 3.1 Application shell

Approved conceptual browser dimensions:

```text
Title bar     ~32 px equivalent
Top bar       ~28 px equivalent
Workspace     remaining height
Prompt area   ~50 px equivalent
Footer        ~24 px equivalent
```

In Textual, exact pixel values are not applicable. Match the visual density and relative proportions rather than literal pixel conversion.

## 3.2 Workspace columns

Use the approved approximate distribution:

```text
Workflow        26%
Center          48% / flexible remainder
Background      26%
```

The center is the primary workspace and should receive the remaining space.

## 3.3 Workspace gap

Use a narrow gutter roughly equivalent to the HTML's compact 8px gap.

## 3.4 Borders

All primary containers and cards use a visual equivalent of:

```text
border radius: 3px
```

Terminal rendering does not support literal 3px radius. Use restrained box borders that preserve the compact visual feel. Do not use oversized rounded panels.

## 3.5 Theme

Preserve the approved dark theme approximately:

```text
background            #07111b
secondary background  #0b1723
panel                  #0a1621 / #08121b
border                 #29445d
strong border          #3478b8
text                   #e8f0f6
muted                  #86a0b5
cyan                   #4db7ff
green                  #37d888
yellow                 #f0c96b
progress track         #203246
```

Use closest supported Textual/Rich terminal colors.

## 3.6 Typography

Use the terminal's normal monospace font. Do not embed or distribute fonts.

---

# 4. Approved Header

The top information bar contains only:

```text
Agent
Model
Session
Active
```

Do not show:

- Git branch
- repository path
- STANDARD/FAST/DEEP mode
- CPU
- memory
- disk
- extra diagnostics

Example:

```text
◉ Agent: component-builder
▣ Model: codex-local (medium)
⌘ Session: 20260909-063501
● Active
```

The title bar above it shows:

```text
Codex Agent Console — Component Builder
```

A small macOS-like traffic-light visual is decorative only.

---

# 5. Approved Workflow Panel

The left panel is the high-level workflow visualization.

It must show:

- `Workflow` title;
- step count;
- percentage;
- very thin progress bar;
- ordered workflow steps;
- status indicator before every step;
- detail lines;
- step elapsed time;
- loop/retry indicator where applicable;
- independent scrolling if content exceeds height.

## 5.1 Hardcoded workflow

Use exactly this initial workflow:

```text
1. Understand request
   - Parse prompt
   - Identify component type

2. Load project context
   - Scan component patterns
   - Read relevant files

3. Generate component
   - Create structure
   - Generate HTML/CSS
   - Validate schema
   - loop until valid

4. Run validations
   - Type check
   - Lint

5. Apply changes
   - Write files
   - Update registry

6. Run tests
   - Execute targeted tests
   - Fix failures if needed
   - retry on failure

7. Finalize
   - Update docs
   - Create concise summary

8. Complete
   - Show result and next steps
```

## 5.2 Step statuses

Support:

```text
pending
running
complete
failed
```

## 5.3 Pending marker

Use a subtle unfilled ring:

```text
○
```

## 5.4 Running marker

Use an animated spinner. Acceptable frames:

```text
◐ ◓ ◑ ◒
```

or a visually equivalent Textual spinner.

Only active/running steps animate.

## 5.5 Complete marker

Completed steps must show a simple green:

```text
✓
```

There must be **no surrounding circle**.

## 5.6 Failed marker

Use a simple red:

```text
×
```

when the failure is terminal.

If the step will retry, keep it active/running and display retry state rather than permanently terminating it.

## 5.7 Loop visualization

Keep loop/retry information attached to the parent step.

Example:

```text
Generate component
  Create structure
  Generate HTML/CSS
  Validate schema
  ↻ loop until valid
```

During retries:

```text
↻ attempt 2
```

Do not create a new workflow row for every retry.

## 5.8 Progress bar

The approved bar is intentionally thin.

Browser reference:

```text
3px
```

Terminal equivalent:

```text
one compact row
```

Do not use a tall/high progress widget.

## 5.9 Progress calculation

For v0.1:

```text
completed steps / total steps
```

Example:

```text
3 / 8
37%
```

---

# 6. Approved Center Panel

The center panel is the primary foreground activity area.

It contains:

1. current activity header;
2. current status;
3. in-progress indicator;
4. one scrolling log/content stream;
5. inline generated artifacts/code.

No tab navigation is required in v0.1.

## 6.1 Current activity header

Example:

```text
Generating component structure…                         ● In progress
```

## 6.2 Logs

Use Textual `RichLog` or equivalent.

Example content:

```text
[06:34:49] Router selected component-builder
[06:34:49] Using model: codex-local (medium)
[06:34:50] Reading relevant project context…
[06:34:51] ✓ Found 12 component patterns
[06:34:52] Analyzing component conventions…
[06:34:54] Generating component structure…
              ├─ Creating component schema
              ├─ Generating HTML template
              ├─ Generating CSS styles
              └─ Validating generated output
[06:35:02] ✓ HTML generation complete
```

Color use:

```text
green   success
cyan    active/current
yellow  warning/retry
red     failure
```

Keep timestamps subdued.

## 6.3 Inline artifacts

Show an artifact header such as:

```text
component.html   +42 lines                                       html
```

Then render code directly below with Rich `Syntax`.

Do not implement a code editor in this phase.

## 6.4 Scrolling

The center content must scroll independently.

Preferred behavior:

- auto-scroll while user remains near bottom;
- if user intentionally scrolls upward, do not force them back down if practical;
- acceptable v0.1 fallback: always auto-scroll.

---

# 7. Approved Background Task Panel

The right panel shows active and queued background work.

Header example:

```text
Background Tasks                                      3 running
```

Do not show:

- CPU usage
- memory usage
- disk usage
- per-task CPU sparklines
- system metrics section

## 7.1 Task fields

Each active task supports:

```text
icon/type
name
elapsed time
description
thin progress bar
command/details
```

Examples:

```text
File Search
Scanning project files…
68%
rg -t ts "component" src/
```

```text
Local Codex Agent
Generating component…
85%
codex run --agent component-builder
```

```text
Type Check
Running in background…
20%
npx tsc --noEmit
```

## 7.2 Progress bar

Use the same compact/one-row treatment as the workflow progress bar.

## 7.3 Queued tasks

Render:

```text
Queued Tasks (2)

◷ Run Tests
  Waiting…

◷ Update Registry
  Waiting…
```

## 7.4 Dynamic task count

For v0.1 a vertical stack is acceptable.

Architecture should support:

```text
1–4 active tasks:
  individual compact cards

5+ active tasks:
  compact list/summary mode
```

Do not split into unreadable micro-panes.

---

# 8. Prompt Input

The bottom input must behave like a Codex-style composer.

Approved visual:

```text
› Type your message here…  (Shift+Enter for new line)
```

Do not show:

```text
Send
Stop
Other
```

buttons.

## 8.1 Behavior

For v0.1:

```text
Enter       submit
Shift+Enter newline
```

Use a Textual `TextArea` or other widget that supports multiline behavior cleanly.

## 8.2 On submit

1. capture text;
2. clear composer;
3. append a user-input log entry;
4. reset/start the selected mock workflow;
5. prompt semantics may remain hardcoded.

Do not pretend the output came from a real model.

---

# 9. Footer

Keep the approved footer simple:

```text
Codex Project Runtime v0.1.0
Local Mode
No API key required
? help
⚙ settings
Ctrl+C exit
```

Real token accounting is not required in v0.1.

---

# 10. Architectural Constraint

The most important engineering rule:

> **UI widgets must not own canonical business state.**

Use:

```text
EventSource
    ↓
Event
    ↓
Reducer / AppState
    ↓
UI renders AppState
```

This allows Phase 2 to replace the mock event source with Codex app-server events without rewriting the TUI.

---

# 11. Recommended Project Structure

Use or adapt to the repository's existing conventions:

```text
codex-agent-console/
│
├── pyproject.toml
├── README.md
│
├── src/
│   └── codex_console/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── workflow.py
│       │   ├── background_task.py
│       │   ├── tokens.py
│       │   └── session.py
│       │
│       ├── state/
│       │   ├── __init__.py
│       │   ├── events.py
│       │   └── app_state.py
│       │
│       ├── mock/
│       │   ├── __init__.py
│       │   ├── workflow.py
│       │   ├── scenarios.py
│       │   └── event_source.py
│       │
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── title_bar.py
│       │   ├── session_bar.py
│       │   ├── workflow_panel.py
│       │   ├── center_panel.py
│       │   ├── background_panel.py
│       │   ├── prompt_bar.py
│       │   └── footer.py
│       │
│       ├── renderers/
│       │   ├── __init__.py
│       │   ├── logs.py
│       │   └── syntax.py
│       │
│       └── styles/
│           └── app.tcss
│
└── tests/
    ├── test_workflow_state.py
    ├── test_background_state.py
    ├── test_events.py
    ├── test_scenarios.py
    └── test_app_smoke.py
```

If an appropriate tools/apps directory already exists in the target repository, place the package there instead of forcing a new top-level location.

---

# 12. Dependencies

Keep dependencies minimal:

```toml
[project]
name = "codex-agent-console"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
  "textual",
  "rich"
]
```

Do not add in Phase 1:

- FastAPI
- Flask
- aiohttp
- Redis
- browser frontend dependencies
- Codex SDK/app-server client
- OpenAI API client
- vector DB

Use dataclasses/Enum unless existing repository standards justify something else.

---

# 13. Core Models

## 13.1 Workflow status

```python
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
```

## 13.2 WorkflowStep

```python
@dataclass
class WorkflowStep:
    id: str
    title: str
    details: list[str]
    status: StepStatus = StepStatus.PENDING
    elapsed_seconds: float | None = None
    loop_enabled: bool = False
    loop_count: int = 0
```

## 13.3 BackgroundTaskStatus

```python
class BackgroundTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
```

## 13.4 BackgroundTask

```python
@dataclass
class BackgroundTask:
    id: str
    name: str
    description: str
    task_type: str
    status: BackgroundTaskStatus
    progress: float | None = None
    elapsed_seconds: float = 0
    command: str | None = None
```

## 13.5 TokenUsage placeholder

```python
@dataclass
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    context_used: int = 0
    context_window: int = 200_000
```

No authoritative token accounting in this phase.

## 13.6 AppState

```python
@dataclass
class AppState:
    workflow: list[WorkflowStep]
    background_tasks: dict[str, BackgroundTask]

    current_step_id: str | None
    current_activity: str
    current_status: str

    logs: list[LogEntry]
    artifacts: list[Artifact]

    agent_name: str
    model_name: str
    session_id: str

    token_usage: TokenUsage
```

---

# 14. Event Architecture

Do not let simulator code update widgets directly.

Create a simple event representation:

```python
@dataclass
class Event:
    type: str
    data: dict[str, Any]
```

Initial event names:

```text
session.started

workflow.started
workflow.step.started
workflow.step.completed
workflow.step.failed
workflow.step.retry
workflow.completed

background.queued
background.started
background.progress
background.completed
background.failed

log.append
artifact.created
artifact.updated

tokens.updated
session.completed
```

All state changes flow through one reducer pattern:

```text
reduce_state(state, event)
```

or:

```text
AppState.apply(event)
```

Pick one and use it consistently.

---

# 15. EventSource Abstraction

Create an interface/protocol immediately:

```python
class EventSource(Protocol):
    async def run(
        self,
        emit: Callable[[Event], Awaitable[None]],
    ) -> None:
        ...
```

Phase 1 implementation:

```text
MockEventSource
```

Future implementation:

```text
CodexAppServerEventSource
```

The UI must not care which source is active.

---

# 16. Canonical Hardcoded Workflow

Store the approved workflow only once in:

```text
mock/workflow.py
```

Do not duplicate workflow definitions inside widgets/scenarios.

---

# 17. Mock Scenarios

Implement at least three.

## 17.1 `happy`

Everything completes successfully.

Validates:

- normal transitions;
- progress;
- logs;
- artifacts;
- background completion.

## 17.2 `retry`

Generation validation fails once and tests fail once before succeeding.

Validates:

- loop indicator;
- warning/error logs;
- retry count;
- running state maintained across retry;
- eventual success.

## 17.3 `busy`

At least five running/queued background tasks.

Validates:

- right-panel overflow;
- task compaction;
- queue rendering;
- independent progress.

Commands:

```bash
codex-console --scenario happy
codex-console --scenario retry
codex-console --scenario busy
```

Default scenario should be `retry` because it exercises more states.

---

# 18. Retry Scenario Timeline

Use a deterministic timeline similar to:

```text
0.0   Understand request → running
0.8   log: Parsing component-builder request
1.8   Understand request → complete

2.0   Load project context → running
2.3   File Search → running
2.5   Project Reader → running
3.2   File Search 35%
4.0   File Search 70%
4.5   File Search complete
5.0   Load project context complete

5.2   Generate component → running
5.4   Local Codex Agent → running
6.0   log: Creating component schema
7.0   artifact: partial component.html
8.0   Local Codex Agent 40%
9.0   log: Generating CSS
10.0  log: Validating output
10.5  warning: schema validation failed
10.6  workflow retry count = 1
10.8  log: ↻ retrying generation
12.0  artifact updated
13.0  Local Codex Agent 90%
14.0  validation succeeds
14.2  Generate component complete

14.5  Run validations → running
14.7  Type Check → running
14.8  Lint → running
16.0  Type Check 50%
16.5  Lint complete
17.0  Type Check complete
17.2  Run validations complete

17.5  Apply changes → running
18.5  Apply changes complete

19.0  Run tests → running
19.1  Run Tests background task → running
20.2  tests fail
20.3  workflow retry count += 1
20.4  log: ↻ fixing test failure
22.0  tests rerun
23.0  tests pass
23.2  Run tests complete

23.5  Finalize → running
24.5  Finalize complete

24.8  Complete → running
25.5  Complete → complete
25.5  session completed
```

Optionally support:

```bash
codex-console --scenario retry --speed 2
```

to speed up manual testing.

---

# 19. Async Background Simulation

Use asyncio.

Example:

```python
await asyncio.gather(
    simulate_file_search(emit),
    simulate_project_reader(emit),
)
```

Later:

```python
await asyncio.gather(
    simulate_typecheck(emit),
    simulate_lint(emit),
)
```

Every concurrent worker emits events through the same pipeline.

No simulator task mutates AppState directly.

---

# 20. Textual Layout

Main hierarchy:

```text
CodexConsoleApp
├── TitleBar
├── SessionBar
├── Workspace
│   ├── WorkflowPanel
│   ├── CenterPanel
│   └── BackgroundPanel
├── PromptBar
└── Footer
```

Use Textual containers appropriate for the layout.

Approximate widths:

```text
Workflow     26%
Center       1fr
Background   26%
```

---

# 21. Widget Responsibilities

## TitleBar

Render:

- traffic-light visual;
- centered title;
- clock.

No business state.

## SessionBar

Render only:

- Agent;
- Model;
- Session;
- Active.

## WorkflowPanel

Render:

- title;
- count;
- percentage;
- thin progress;
- status markers;
- detail lines;
- retry labels;
- elapsed times.

Must not own canonical workflow state.

## CenterPanel

Render:

- current activity;
- current status;
- streaming logs;
- inline artifacts/code.

No tabs.

## BackgroundPanel

Render:

- running count;
- task cards;
- queued tasks.

No system metrics.

## PromptBar

Own input interaction only, not workflow state.

## Footer

Render static runtime/help information.

---

# 22. Rendering Strategy

Use the simplest reliable primitives.

Recommended:

```text
workflow             Textual widgets or Rich renderable
center log           RichLog
inline code          Rich Syntax
background progress  compact Textual/custom one-row bar
prompt                TextArea or appropriate multiline input
```

Avoid custom low-level terminal drawing unless necessary.

---

# 23. Spinner

Preferred order:

1. Textual built-in spinner if compact enough;
2. custom timer-driven frames:

```text
◐ ◓ ◑ ◒
```

Use roughly 100–150 ms animation interval.

Do not animate pending steps.

---

# 24. Central State Refresh

Conceptual flow:

```python
async def on_event(event: Event) -> None:
    reduce_state(state, event)
    refresh_ui_from_state(state)
```

Do not scatter widget mutation calls throughout mock scenario code.

The simulator knows only:

```text
emit(Event)
```

---

# 25. Prompt Submission

When user enters:

```text
build a pricing card
```

v0.1 should:

1. append a user log line;
2. reset workflow/background/artifact state;
3. launch selected mock scenario;
4. keep generated component semantics hardcoded.

Do not claim a real model generated it.

---

# 26. Cancellation

Prefer to make the simulation task cancellable.

Acceptable initial behavior:

```text
Ctrl+C = exit
```

Better behavior if easy:

```text
first Ctrl+C during active run = cancel simulation
second Ctrl+C / Ctrl+Q         = exit
```

Do not add visible Stop buttons.

---

# 27. Resize Requirements

Manually verify:

```text
wide terminal
medium terminal
narrow but still usable terminal
```

Recommended minimum:

```text
120 columns × 35 rows
```

At smaller sizes:

- keep center usable;
- allow independent scrolling;
- compress side detail if needed;
- never crash.

---

# 28. Error Handling

If simulation raises:

1. keep app alive;
2. mark active workflow step failed;
3. append concise error log;
4. set current status failed;
5. allow another prompt/run.

Do not crash the entire TUI because a mock task failed.

---

# 29. Developer Logging

Visible center logs are product logs.

Python debug/errors should go separately, e.g.:

```text
/tmp/codex-agent-console.log
```

Do not mix framework debug output into simulated Codex activity.

---

# 30. Unit Tests

Focus on state/event correctness, not pixel-perfect snapshots.

Required workflow tests:

```text
pending → running
running → complete
running → retry
running → failed
retry count increments
progress percentage correct
```

Required background tests:

```text
queued → running
progress updates
running → complete
running → failed
running count correct
queued count correct
```

Reducer tests:

```text
log append
artifact creation
artifact update
current activity update
session reset
```

Scenario tests:

- happy eventually completes;
- retry emits generation retry;
- retry emits test retry;
- busy creates 5+ background task states;
- successful scenarios emit session completion.

Prompt/reset test:

- new prompt resets prior run correctly.

---

# 31. Textual Smoke Test

If Textual test tooling is available, add one smoke test that:

1. launches app;
2. confirms major widgets exist;
3. emits mock event;
4. verifies no render exception;
5. submits a prompt;
6. exits cleanly.

Do not over-invest in pixel snapshots for v0.1.

---

# 32. README

Document:

```text
requirements
install
run
scenarios
keyboard controls
architecture
current limitations
future Codex integration
```

Example:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
codex-console --scenario retry
```

---

# 33. Parallel Agent Strategy

The coordinator must use parallel worker agents where file ownership is clean.

Do **not** have multiple workers modifying the same files concurrently.

The coordinator owns:

- repository discovery;
- architecture decisions;
- shared interfaces;
- task assignment;
- merge/integration;
- final validation;
- nothing-missed audit.

---

# 34. Batch 0 — Coordinator Bootstrap

**Run alone before parallel work.**

Tasks:

1. inspect repository;
2. choose exact package location;
3. read applicable AGENTS/project instructions;
4. create package skeleton;
5. create initial `pyproject.toml`;
6. define shared state/event contracts;
7. create placeholder modules;
8. define canonical event names;
9. define canonical workflow model interfaces;
10. make sure workers can work without redefining contracts.

Coordinator must lock/create shared contracts before spawning workers:

```text
models/workflow.py
models/background_task.py
models/tokens.py
state/events.py
state/app_state.py interface
```

Workers must not independently rename event types.

---

# 35. Parallel Batch 1

Run these workers in parallel.

## Worker A — State & Reducer

**Exclusive ownership:**

```text
src/codex_console/models/*
src/codex_console/state/*
tests/test_workflow_state.py
tests/test_background_state.py
tests/test_events.py
```

Tasks:

- enums/dataclasses;
- Event model;
- AppState/reducer;
- workflow progress calculation;
- reset logic;
- log/artifact models;
- unit tests.

Must not modify UI files.

Return:

```text
files changed
state API
event types
tests run
known limitations
```

## Worker B — Workflow UI

**Exclusive ownership:**

```text
src/codex_console/widgets/workflow_panel.py
```

May add a workflow-specific renderer only if needed.

Tasks:

- workflow title/count/percentage;
- thin progress bar;
- pending ring;
- animated spinner;
- simple green tick without circle;
- failed marker;
- detail lines;
- retry/loop badge;
- elapsed time;
- independent scrolling;
- compact spacing matching approved HTML.

Must consume shared state only.

## Worker C — Center UI

**Exclusive ownership:**

```text
src/codex_console/widgets/center_panel.py
src/codex_console/renderers/logs.py
src/codex_console/renderers/syntax.py
```

Tasks:

- current activity header;
- status indicator;
- scrolling RichLog;
- timestamp styling;
- success/current/warning/failure styling;
- inline artifact header;
- inline Rich Syntax code;
- auto-scroll behavior.

Must **not** introduce tabs.

## Worker D — Background UI

**Exclusive ownership:**

```text
src/codex_console/widgets/background_panel.py
```

Tasks:

- header/running count;
- compact cards;
- task icon/name/time;
- description;
- thin progress bar;
- command text;
- queued section;
- 5+ task compact behavior;
- independent scrolling.

Must not add CPU/memory/disk/system stats.

---

# 36. Coordinator Integration Gate 1

After Batch 1:

1. inspect every worker diff;
2. verify shared interfaces match UI consumers;
3. resolve naming inconsistencies;
4. run state/reducer tests;
5. import worker modules;
6. check for circular imports;
7. ensure no worker modified unauthorized files;
8. stabilize contracts before Batch 2.

Do not continue if event/state contracts are inconsistent.

---

# 37. Parallel Batch 2

Run after Gate 1.

## Worker E — Shell / Styling / Prompt

**Exclusive ownership:**

```text
src/codex_console/app.py
src/codex_console/widgets/title_bar.py
src/codex_console/widgets/session_bar.py
src/codex_console/widgets/prompt_bar.py
src/codex_console/widgets/footer.py
src/codex_console/styles/app.tcss
src/codex_console/__main__.py
```

Tasks:

- five-region layout;
- 26/flexible/26 workspace;
- approved header fields only;
- title bar;
- footer;
- prompt behavior;
- focus/keybindings;
- resize behavior;
- AppState wiring;
- app-level `emit_event()`/event handling entrypoint.

Must not duplicate reducer logic.

## Worker F — Mock Event Engine

**Exclusive ownership:**

```text
src/codex_console/mock/*
tests/test_scenarios.py
```

Tasks:

- canonical hardcoded workflow;
- MockEventSource;
- happy/retry/busy scenarios;
- deterministic timeline;
- asyncio concurrency;
- retry events;
- background progress;
- artifact updates;
- speed multiplier if practical;
- cancellation support where practical.

Must emit events only.

Must never call UI widget methods.

## Worker G — Packaging / README / Smoke Test

**Exclusive ownership:**

```text
README.md
tests/test_app_smoke.py
```

May propose `pyproject.toml` changes but coordinator should apply if shared.

Tasks:

- install/run docs;
- scenarios;
- keybindings;
- architecture explanation;
- limitations;
- smoke test;
- developer workflow.

---

# 38. Worker Coordination Rules

Every worker must:

1. read shared contracts before coding;
2. modify only assigned files unless coordinator approves expansion;
3. not redesign UI;
4. not rename shared event types;
5. not add dependencies without approval;
6. not integrate real Codex yet;
7. run targeted tests;
8. return a compact integration handoff.

Handoff format:

```text
STATUS: COMPLETED | BLOCKED

Task:
Files changed:
Interfaces used:
Tests run:
Manual checks:
Potential integration conflicts:
Coordinator notes:
```

---

# 39. Coordinator Integration Gate 2

After Batch 2:

1. wire AppState to all panels;
2. wire EventSource → reducer → UI refresh;
3. launch scenarios;
4. wire prompt submit → reset → scenario start;
5. confirm simulator never mutates widgets;
6. confirm widgets never own canonical state;
7. run all tests;
8. perform manual TUI review.

---

# 40. Manual Visual Review Checklist

Compare against approved HTML.

## Header

- [ ] title is `Codex Agent Console — Component Builder`
- [ ] traffic-light visual exists
- [ ] Agent shown
- [ ] Model shown
- [ ] Session shown
- [ ] Active shown
- [ ] no Git
- [ ] no execution mode
- [ ] no CPU/memory/disk

## Layout

- [ ] left/right approximately equal width
- [ ] center is largest
- [ ] compact gaps
- [ ] compact density
- [ ] restrained borders

## Workflow

- [ ] title
- [ ] step count
- [ ] percentage
- [ ] thin progress bar
- [ ] pending ring
- [ ] running spinner
- [ ] completed simple green tick
- [ ] completed tick has no circle
- [ ] details
- [ ] elapsed time
- [ ] retry/loop indicator
- [ ] independent scroll

## Center

- [ ] current activity
- [ ] in-progress state
- [ ] logs
- [ ] timestamps
- [ ] success color
- [ ] warning/retry style
- [ ] inline artifact header
- [ ] inline syntax-highlighted code
- [ ] no tabs
- [ ] independent scrolling

## Background

- [ ] title
- [ ] running count
- [ ] task icon
- [ ] task name
- [ ] elapsed time
- [ ] description
- [ ] thin progress bar
- [ ] command
- [ ] queued section
- [ ] no system metrics
- [ ] no task CPU graphs
- [ ] independent scrolling

## Prompt

- [ ] Codex-style chevron
- [ ] no Send button
- [ ] no Stop button
- [ ] no Other button
- [ ] Enter submits
- [ ] Shift+Enter newline

## Footer

- [ ] version
- [ ] Local Mode
- [ ] No API key required
- [ ] help
- [ ] settings
- [ ] exit hint

---

# 41. Behavior Review Checklist

## Workflow

- [ ] pending → running works
- [ ] spinner animates
- [ ] running → complete gives simple green ✓
- [ ] terminal failed state visible
- [ ] retry keeps step active
- [ ] retry count changes
- [ ] overall progress changes
- [ ] final completion works

## Background

- [ ] tasks queue
- [ ] queued task starts
- [ ] multiple tasks run concurrently
- [ ] progress updates independently
- [ ] tasks complete
- [ ] failure renders
- [ ] 5+ task case remains readable

## Center

- [ ] logs stream over time
- [ ] code artifact appears
- [ ] artifact can update
- [ ] warning/retry logs display
- [ ] final success log displays

## Prompt

- [ ] prompt submission starts/restarts scenario
- [ ] text clears after submit
- [ ] multiline behavior works
- [ ] multiple runs within one app process work

## App lifecycle

- [ ] app launches cleanly
- [ ] app exits cleanly
- [ ] cancellation/exit is safe
- [ ] simulator exception does not corrupt state
- [ ] resize does not crash app

---

# 42. Automated Verification

Run at minimum:

```bash
python -m compileall src
pytest
```

Also manually run:

```bash
codex-console --scenario happy
codex-console --scenario retry
codex-console --scenario busy
```

If target repository has standard lint/typecheck commands for Python tooling, run them too.

---

# 43. Final Nothing-Missed Audit

Before completion, coordinator must explicitly audit every requirement.

Use sections:

```text
3–9    UI contract
10–16  architecture
17–19  scenarios/concurrency
20–29  runtime/interaction
30–32  tests/docs
40–41  visual/behavior review
```

For each requirement classify:

```text
PASS
PARTIAL
NOT IMPLEMENTED
NOT APPLICABLE
```

No item may be silently skipped.

For every `PARTIAL` or `NOT IMPLEMENTED` item:

- explain why;
- state whether it blocks v0.1;
- create a follow-up item.

---

# 44. Cross-Worker Diff Audit

Coordinator must run:

```bash
git status --short
git diff --stat
git diff
```

Confirm:

- no unrelated application code changed;
- no duplicate state models;
- no duplicate workflow definitions;
- no unused experimental files;
- no accidental real Codex/API integration;
- no unnecessary dependency;
- no tabs reintroduced;
- no system metrics reintroduced;
- no extra prompt buttons reintroduced.

---

# 45. Dependency Audit

Expected runtime dependencies:

```text
textual
rich
```

plus existing repository test tooling.

Remove accidental dependencies introduced by workers.

---

# 46. Architecture Audit

The final Phase 1 architecture must be:

```text
MockEventSource
       ↓
     Event
       ↓
    Reducer
       ↓
    AppState
       ↓
       UI
```

There must be no dependency such as:

```text
mock scenario → workflow widget
```

or:

```text
widget → mock scenario implementation
```

This boundary is critical for Phase 2.

---

# 47. Future Codex Integration Boundary

Do not implement now.

Document that Phase 2 replaces:

```text
MockEventSource
```

with:

```text
CodexAppServerEventSource
```

and normalizes real Codex events into the same internal Event model.

Future conceptual mapping:

```text
turn started        → session/workflow event
command execution   → background task
subagent started    → background agent task
file change         → inline artifact/diff
approval request    → future approval UI
token usage         → future token state
turn completed      → completion state
```

The TUI/state architecture should not require major rewrites when this happens.

---

# 48. Out-of-Scope Guard

Do not expand Phase 1 into:

- real Codex app-server
- local Codex execution
- OpenAI API
- token billing/accounting
- permission dialogs
- real file editing
- real shell execution
- persistent session history
- SQLite
- session logging
- router agents
- AWS
- SQS
- browser frontend
- WebSockets
- semantic/vector memory

Build only the UI/state/mock-event foundation.

---

# 49. Required Parallel Execution Order

The coordinator should use:

```text
BATCH 0
Coordinator establishes shared contracts

BATCH 1 — parallel
├── Worker A: state/reducer
├── Worker B: workflow UI
├── Worker C: center UI
└── Worker D: background UI

INTEGRATION GATE 1

BATCH 2 — parallel
├── Worker E: shell/prompt/styling
├── Worker F: mock event engine
└── Worker G: README/smoke tests

INTEGRATION GATE 2

FULL TESTS
MANUAL REVIEW
NOTHING-MISSED AUDIT
```

Do not spawn every worker before shared contracts exist.

---

# 50. Worker Efficiency Rules

Workers should:

- read only assigned files and required shared contracts;
- avoid repeatedly scanning the entire repository;
- use concise progress updates;
- run targeted tests first;
- avoid speculative abstractions;
- preserve the approved UI;
- report compact handoffs.

Coordinator should give every worker:

```text
task
exclusive file ownership
shared interfaces
acceptance criteria
non-goals
```

instead of sending unnecessary full-history context.

---

# 51. Completion Definition

Phase 1 is complete when:

1. Python Textual app launches from one CLI command;
2. visual hierarchy matches approved HTML;
3. workflow spinner/tick/retry states work;
4. background concurrency works;
5. center logs and inline code update;
6. prompt works;
7. happy/retry/busy scenarios work;
8. tests pass;
9. resize/manual review passes;
10. event-source-independent architecture is preserved;
11. final audit has no unexplained missed requirement;
12. no real Codex integration has leaked into v0.1.

---

# 52. Final Coordinator Report

Return:

```text
Implementation status:

Parallel workers used:
- ...

Files created/changed:
- ...

Scenarios:
- happy
- retry
- busy

Tests:
- ...

Manual UI review:
- ...

Approved-HTML deviations:
- none
```

If deviations exist:

```text
Deviation:
Reason:
Impact:
Follow-up:
```

Also provide exact run command, for example:

```bash
codex-console --scenario retry
```

---

# 53. Final Instruction to the Worker Coordinator

Implement this plan in staged parallel work.

Do not merely describe it.

Before spawning workers:

1. inspect the repository;
2. establish shared state/event contracts;
3. assign exclusive file ownership.

Then execute:

```text
Parallel Batch 1
→ Integration Gate 1
→ Parallel Batch 2
→ Integration Gate 2
→ full tests
→ manual UI review
→ nothing-missed audit
```

The approved HTML is the design contract.

Do not redesign the UI unless a terminal implementation limitation makes an exact translation impossible.

When terminal limitations require an adaptation, preserve the visual hierarchy, compact density, colors, and behavior as closely as possible and document the adaptation.

The most important engineering constraint is:

> Keep the TUI fully driven by AppState/events so the hardcoded `MockEventSource`
> can later be replaced by a real Codex app-server event source without rewriting
> the UI.
