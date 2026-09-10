"""Input validation for the local interactive web-search CLI."""


from typing import Any


def validate_payload(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Validate a request and return its resolved search-profile mapping.

    ``ValueError`` messages are deliberately actionable because this module is
    called before Selenium or Chrome are started.
    """
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a dictionary.")

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("A non-blank prompt is required.")

    if not isinstance(config, dict):
        raise ValueError("Search configuration must be a dictionary.")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("Search configuration must define profiles.")

    profile_name = payload.get("profile") or config.get("active_profile")
    if not isinstance(profile_name, str) or not profile_name:
        raise ValueError("A search profile must be selected.")

    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise ValueError(f"Unknown search profile: {profile_name}")
    if not profile.get("enabled"):
        raise ValueError(f"Search profile is disabled: {profile_name}")
    if not isinstance(profile.get("url"), str) or not profile["url"].strip():
        raise ValueError(f"Search profile '{profile_name}' requires a URL.")
    if (
        not isinstance(profile.get("prompt_selector"), str)
        or not profile["prompt_selector"].strip()
    ):
        raise ValueError(
            f"Search profile '{profile_name}' requires a prompt selector."
        )

    return profile
