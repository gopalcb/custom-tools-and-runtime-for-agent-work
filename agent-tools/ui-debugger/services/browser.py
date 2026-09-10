"""Selenium interactions for the local Chrome-backed search tool."""

import os
import time
from typing import Any

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
except ImportError as error:  # Selenium is installed by the standalone tool.
    webdriver = None
    WebDriverException = ImportError
    By = None
    Keys = None
    SELENIUM_IMPORT_ERROR = error
else:
    SELENIUM_IMPORT_ERROR = None


def _setting(config: dict[str, Any], name: str, default: Any) -> Any:
    """Read a browser setting, falling back to the supplied default."""
    return config.get("browser", {}).get(name, default)


def _visible_element(driver: Any, selector: str) -> Any | None:
    """Return the first enabled, visible element matching a CSS selector."""
    for element in driver.find_elements(By.CSS_SELECTOR, selector):
        if element.is_displayed() and element.is_enabled():
            return element
    return None


def _find_prompt_input(
    driver: Any,
    profile: dict[str, Any],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> Any:
    """Find the configured prompt box, then a visible rich-editor fallback."""
    deadline = time.monotonic() + timeout_seconds
    selectors = [profile["prompt_selector"]]
    fallback = profile.get("visible_editor_selector")
    if fallback and fallback not in selectors:
        selectors.append(fallback)

    while time.monotonic() < deadline:
        for selector in selectors:
            element = _visible_element(driver, selector)
            if element is not None:
                return element
        time.sleep(poll_interval_seconds)
    raise RuntimeError("Could not find a visible prompt input before timeout.")


def _submit_prompt(
    driver: Any, prompt_input: Any, profile: dict[str, Any], prompt: str
) -> None:
    """Submit a prompt with Enter, or use the configured send button."""
    prompt_input.click()
    try:
        prompt_input.clear()
    except WebDriverException:
        # contenteditable elements do not consistently implement clear().
        pass
    prompt_input.send_keys(prompt)
    try:
        prompt_input.send_keys(Keys.ENTER)
        return
    except WebDriverException:
        pass

    send_button = profile.get("send_button_selector")
    if send_button:
        for button in driver.find_elements(By.CSS_SELECTOR, send_button):
            if button.is_displayed() and button.is_enabled():
                button.click()
                return
    raise RuntimeError("Could not submit the prompt with Enter or the send button.")


def start_search(
    config: dict[str, Any], profile: dict[str, Any], prompt: str
) -> tuple[Any, int]:
    """Open Chrome, submit *prompt*, and return ``(driver, prior_count)``."""
    if webdriver is None:
        raise RuntimeError(
            "Selenium is required for interactive web search; install requirements.txt"
        ) from SELENIUM_IMPORT_ERROR

    from selenium import webdriver
    from selenium.webdriver.common.by import By

    user_data_dir = os.environ.get(
        "CHROME_USER_DATA_DIR",
        _setting(config, "user_data_dir", "~/Library/Application Support/Google/Chrome"),
    )
    profile_directory = os.environ.get(
        "CHROME_PROFILE_DIRECTORY", _setting(config, "profile_directory", "Default")
    )
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={os.path.expanduser(user_data_dir)}")
    options.add_argument(f"--profile-directory={profile_directory}")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(_setting(config, "page_load_timeout_seconds", 30))
    try:
        driver.get(profile["url"])
        prior_count = len(
            driver.find_elements(By.CSS_SELECTOR, profile.get("assistant_selector", ""))
        )
        prompt_input = _find_prompt_input(
            driver,
            profile,
            _setting(config, "prompt_timeout_seconds", 30),
            _setting(config, "poll_interval_seconds", 0.5),
        )
        _submit_prompt(driver, prompt_input, profile, prompt)
        return driver, prior_count
    except Exception:
        driver.quit()
        raise
