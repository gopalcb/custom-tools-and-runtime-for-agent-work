# Interactive Web Search Tool

Target location in the monorepo:

```text
monorepo/tools/interactive-web-search/
```

## 1. Purpose

`interactive-web-search` is a small local tool that lets an agent run a browser-backed search using the user's existing Chrome profile/session.

The first implementation supports:

- **ChatGPT** as the active search profile.
- **Google** as a configured-but-not-yet-specialized search profile.
- A **CLI entry point** for local execution.
- Selenium-driven Chrome using the configured local Chrome profile so existing cookies/session can be reused.
- Prompt submission.
- Waiting for the ChatGPT response to finish.
- Extracting elements matching `data-message-author-role="assistant"`.
- Saving the newest extracted assistant response to a Markdown file.

The API file is intentionally left as a placeholder until the CLI path is proven reliable.

---

## 2. Design Principles

1. **Keep file count low.**
   - No repository layer, adapters, DTOs, controllers, factories, or plugin system yet.
   - Add abstractions only when a second real implementation requires them.

2. **Separate only the responsibilities that materially differ.**
   - Browser interaction.
   - Response extraction/storage.
   - Input validation.
   - CLI orchestration.

3. **Configuration over duplicated code.**
   - Search targets/selectors live in one YAML file.
   - The same CLI flow resolves whichever profile is active.

4. **Local-first.**
   - Browser execution happens on the developer machine.
   - Existing browser cookies remain in the user's Chrome profile.
   - No cookie export or credential persistence is added by this tool.

5. **Selector resilience without overengineering.**
   - Use the requested ChatGPT textarea as the primary selector.
   - Include one small visible-editor fallback because ChatGPT may keep the fallback textarea hidden.
   - Determine response completion primarily through text stability rather than depending on a single UI button.

---

## 3. Compact Directory Structure

```text
interactive-web-search/
├── ARCHITECTURE.md
├── search-config.yaml
├── requirements.txt
├── cli.py
├── api.py
└── services/
    ├── browser.py
    ├── extractor.py
    └── validation.py
```

### Why there is no `__init__.py`

For this simple Python 3 local tool, `services` can work as a namespace package when `cli.py` is executed from the project directory. Add `__init__.py` later only if packaging/import tooling requires it.

---

## 4. File Responsibilities

### `search-config.yaml`

Single source of configuration for:

- Chrome user-data root.
- Chrome profile directory.
- Selenium timeouts.
- Available search profiles.
- Active search profile.
- Prompt/assistant CSS selectors.

Current profiles:

- `chatgpt` — active and implemented.
- `google` — registered for future implementation.

The active ChatGPT project URL is:

```text
https://chatgpt.com/g/g-p-6aa1e5d028a4819192303e47ac7c6180/project
```

### `services/validation.py`

Contains one intentionally small validation function:

```python
validate_payload(payload, config)
```

It checks:

- Payload is a dictionary.
- Prompt exists and is not blank.
- Search profile exists.
- Search profile is enabled.
- URL and prompt selector are configured.

It also returns the resolved profile so validation and profile resolution do not need separate modules.

### `services/browser.py`

Responsible only for Selenium/browser actions:

1. Resolve Chrome profile settings.
2. Open Chrome with the configured user profile.
3. Navigate to the active search URL.
4. Count existing assistant messages before submission.
5. Locate the prompt input.
6. Enter the prompt.
7. Submit with Enter, with a small send-button fallback.

Primary ChatGPT prompt selector:

```css
textarea[name="prompt-textarea"]
```

The exact textarea can be present but hidden, so `browser.py` includes a visible `contenteditable` fallback. This prevents the entire tool from failing when the fallback textarea is not interactable.

### `services/extractor.py`

Responsible for:

1. Waiting until a new assistant message appears.
2. Polling the newest assistant message.
3. Declaring it complete after the text remains unchanged for a configured stability window.
4. Reading all matching assistant DOM elements.
5. Saving the newest assistant response into a timestamped Markdown file.

Assistant selector:

```css
[data-message-author-role="assistant"]
```

Runtime output is created only when a search runs:

```text
output/interactive-search-YYYYMMDD_HHMMSS.md
```

The output contains:

- Search profile.
- Timestamp.
- Prompt.
- Latest assistant response.

### `cli.py`

The only implemented entry point in v1.

Responsibilities:

1. Load YAML.
2. Build the payload.
3. Validate/resolve the payload.
4. Start browser/search.
5. Wait/extract.
6. Save Markdown.
7. Close Chrome unless `--keep-browser-open` is provided.

A hardcoded default testing prompt is included, so the first run requires no arguments.

### `api.py`

Reserved for a future localhost endpoint.

No web framework is added yet. This avoids introducing Flask/FastAPI before the Selenium workflow itself is stable.

### `requirements.txt`

Only two direct dependencies:

```text
selenium
PyYAML
```

Modern Selenium can use Selenium Manager to resolve a compatible Chrome driver in typical environments, avoiding a custom driver-management module.

---

## 5. Execution Workflow

```text
Agent / Developer
      │
      ▼
    cli.py
      │
      ├── load search-config.yaml
      │
      ├── validation.validate_payload(...)
      │
      ▼
browser.start_search(...)
      │
      ├── open Chrome with current configured profile
      ├── navigate to active profile URL
      ├── count existing assistant messages
      ├── set prompt
      └── submit
      │
      ▼
extractor.wait_for_complete_response(...)
      │
      ├── wait for a new assistant element
      ├── monitor latest response text
      └── return when response is stable
      │
      ▼
extractor.save_markdown(...)
      │
      ▼
output/*.md
```

---

## 6. Configuration

Default macOS Chrome setup:

```yaml
browser:
  user_data_dir: "~/Library/Application Support/Google/Chrome"
  profile_directory: "Default"
```

If the signed-in Chrome profile is not `Default`, inspect the Chrome profile directory and change it to something such as:

```yaml
profile_directory: "Profile 1"
```

Environment overrides are also supported without modifying YAML:

```bash
export CHROME_USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome"
export CHROME_PROFILE_DIRECTORY="Profile 1"
```

### Important Chrome profile limitation

Chrome commonly prevents two processes from opening the same user-data/profile directory simultaneously.

For the first implementation, the simplest operating rule is:

1. Close regular Chrome before running this CLI if the profile is locked.
2. Run the Selenium CLI.
3. Let Selenium open Chrome using that same local profile/session.

If simultaneous normal-Chrome + automation becomes a requirement later, add a separate explicit remote-debugging/attach mode rather than complicating this initial version.

---

## 7. Install and Run

From:

```text
monorepo/tools/interactive-web-search/
```

Create/activate a virtual environment if desired, then:

```bash
pip install -r requirements.txt
```

Run the hardcoded test prompt:

```bash
python cli.py
```

Run a custom prompt:

```bash
python cli.py --prompt "Research the latest approaches to agent memory architecture"
```

Explicitly choose the search profile:

```bash
python cli.py --profile chatgpt --prompt "Explain hybrid search for agent memory"
```

Keep Chrome open for selector/debug testing:

```bash
python cli.py --keep-browser-open
```

---

## 8. Detailed Implementation Plan

### Phase 1 — Baseline CLI

Status represented by this scaffold: **implemented**.

Tasks:

1. Create compact directory structure.
2. Add YAML configuration.
3. Add ChatGPT and Google profile definitions.
4. Set ChatGPT as active profile.
5. Add hardcoded default prompt.
6. Validate payload before browser initialization.
7. Start Selenium Chrome using configured profile.
8. Navigate to the configured ChatGPT project.
9. Enter and submit prompt.
10. Wait for new assistant response.
11. Wait until response text stabilizes.
12. Extract assistant elements using `data-message-author-role="assistant"`.
13. Store latest assistant response in Markdown.
14. Close browser by default.

### Phase 2 — Verify Against Real ChatGPT DOM

Run locally and confirm:

- The configured Chrome profile is the logged-in profile.
- ChatGPT project opens without a login redirect.
- Primary textarea selector is found.
- Visible-editor fallback works when the textarea is hidden.
- Enter submission works.
- Assistant elements match the configured selector.
- The stability interval does not stop too early during long streamed responses.

Only modify selectors/configuration if actual DOM behavior requires it.

### Phase 3 — Harden Browser Lifecycle

After the baseline works reliably:

- Add a clearer message for Chrome profile lock errors.
- Optionally add `--profile-directory` CLI override if developers frequently switch profiles.
- Optionally add attach-to-existing-debug-Chrome mode if simultaneous use is required.

Do **not** add this complexity before it is needed.

### Phase 4 — Add Google Search Behavior

Keep the same orchestration and implement profile-specific extraction only when Google becomes a real requirement.

Likely additions can remain inside existing modules initially:

- Submit Google query.
- Extract result blocks.
- Normalize result title/link/snippet.
- Save Markdown using the same output function or a small generalized version.

Do not create a separate `google_service.py` unless Google behavior becomes sufficiently large to justify it.

### Phase 5 — Local API

Only after the CLI is stable:

1. Choose Flask or FastAPI.
2. Implement a single local endpoint, for example:

```text
POST /search
```

Payload:

```json
{
  "prompt": "...",
  "profile": "chatgpt"
}
```

3. Reuse exactly the same validation/browser/extractor functions used by the CLI.
4. Do not duplicate orchestration logic between `cli.py` and `api.py`; if both become non-trivial, extract one small shared `run_search(...)` function at that time.

---

## 9. Recommended Next Refactor Point

Do **not** refactor preemptively.

The first justified shared abstraction is likely this function:

```python
run_search(payload, config) -> result
```

Add it only when `api.py` becomes active, because then both CLI and API will need identical orchestration.

Until then, keeping orchestration in `cli.py` is simpler and easier to understand.

---

## 10. Security and Operational Notes

- The tool intentionally reuses a local Chrome profile, which means the automated browser can act within sessions already authenticated in that profile.
- Do not log cookies, authorization headers, local-storage tokens, or browser profile contents.
- Keep the tool local-only initially.
- Do not expose the future API beyond localhost without authentication and an explicit security review.
- Avoid persisting full page HTML unless there is a concrete debugging requirement; save only the extracted response needed by the agent workflow.
- Review the target site's terms and automation policies before using the tool at scale.

---

## 11. Acceptance Criteria for v1

The first version is complete when all of the following work locally:

- `python cli.py` runs with no prompt argument.
- Validation occurs before Chrome opens.
- Chrome opens with the intended existing profile/session.
- The configured ChatGPT project opens.
- The hardcoded prompt is submitted.
- The tool detects a new assistant response.
- The tool waits until response text stops changing.
- The tool extracts ChatGPT assistant message text.
- A Markdown result file is written under `output/`.
- Chrome closes cleanly by default.
- `api.py` remains non-operational by design.
