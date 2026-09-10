"""Assistant-response extraction and Markdown persistence."""

from datetime import datetime
from pathlib import Path
import time
from typing import Any

try:
    from selenium.webdriver.common.by import By
except ImportError as error:  # Selenium is installed by the standalone tool.
    By = None
    SELENIUM_IMPORT_ERROR = error
else:
    SELENIUM_IMPORT_ERROR = None


def extract_assistant_messages(driver: Any, profile: dict[str, Any]) -> list[str]:
    """Return non-empty assistant messages in page order."""
    if By is None:
        raise RuntimeError(
            "Selenium is required for interactive web search; install requirements.txt"
        ) from SELENIUM_IMPORT_ERROR
    selector = profile.get("assistant_selector")
    if not selector:
        raise ValueError("The selected profile does not define an assistant selector.")
    return [
        element.text.strip()
        for element in driver.find_elements(By.CSS_SELECTOR, selector)
        if element.text.strip()
    ]


def wait_for_complete_response(
    driver: Any,
    profile: dict[str, Any],
    config: dict[str, Any],
    prior_count: int,
) -> str:
    """Return the newest response once it has stopped changing briefly."""
    browser = config.get("browser", {})
    timeout = browser.get("response_timeout_seconds", 180)
    stability_window = browser.get("response_stability_seconds", 3)
    poll_interval = browser.get("poll_interval_seconds", 0.5)
    deadline = time.monotonic() + timeout
    newest_text = ""
    last_change = None

    while time.monotonic() < deadline:
        messages = extract_assistant_messages(driver, profile)
        if len(messages) > prior_count:
            current = messages[-1]
            now = time.monotonic()
            if current != newest_text:
                newest_text = current
                last_change = now
            elif last_change is not None and now - last_change >= stability_window:
                return newest_text
        time.sleep(poll_interval)

    raise TimeoutError("Timed out waiting for a stable assistant response.")


def save_markdown(
    profile_name: str,
    prompt: str,
    response: str,
    output_directory: str = "output",
) -> Path:
    """Save one response and return the path to its timestamped Markdown file."""
    timestamp = datetime.now().astimezone()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    base_name = f"interactive-search-{timestamp:%Y%m%d_%H%M%S}"
    path = output / f"{base_name}.md"
    suffix = 1
    while path.exists():
        path = output / f"{base_name}-{suffix}.md"
        suffix += 1

    path.write_text(
        "# Interactive Search Result\n\n"
        f"- Search profile: {profile_name}\n"
        f"- Timestamp: {timestamp.isoformat()}\n\n"
        "## Prompt\n\n"
        f"{prompt.strip()}\n\n"
        "## Latest assistant response\n\n"
        f"{response.strip()}\n",
        encoding="utf-8",
    )
    return path
