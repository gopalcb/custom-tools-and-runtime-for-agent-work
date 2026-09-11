"""Shared runtime for the local agent control plane."""

from .logging_config import configure_runtime_logging

configure_runtime_logging()

__all__ = ["configure_runtime_logging"]
