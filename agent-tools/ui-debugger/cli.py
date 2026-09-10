"""Run a local browser-backed ChatGPT search using an existing Chrome profile."""

import argparse
from pathlib import Path
from typing import Any

import yaml

from services.browser import start_search
from services.extractor import save_markdown, wait_for_complete_response
from services.validation import validate_payload

DEFAULT_PROMPT = "Briefly explain how a local agent can use web search responsibly."
CONFIG_PATH = Path(__file__).with_name("search-config.yaml")


def load_config(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    """Load and validate the YAML search configuration mapping."""
    with Path(path).open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError("Search configuration must contain a YAML mapping.")
    return config


def parse_args() -> argparse.Namespace:
    """Parse command-line options for one interactive search."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt to submit.")
    parser.add_argument("--profile", help="Configured search profile to use.")
    parser.add_argument(
        "--keep-browser-open",
        action="store_true",
        help="Leave Chrome open after saving the response for selector debugging.",
    )
    return parser.parse_args()


def main() -> None:
    """Run one browser-backed search and persist its response."""
    args = parse_args()
    config = load_config()
    payload = {"prompt": args.prompt, "profile": args.profile}
    profile = validate_payload(payload, config)
    profile_name = args.profile or config["active_profile"]

    driver = None
    try:
        driver, prior_count = start_search(config, profile, args.prompt)
        response = wait_for_complete_response(driver, profile, config, prior_count)
        output_path = save_markdown(profile_name, args.prompt, response)
        print(f"Saved latest assistant response to {output_path}")
    finally:
        if driver is not None and not args.keep_browser_open:
            driver.quit()


if __name__ == "__main__":
    main()
