"""Contracts for the Selenium UI debugger tool."""

from .runner import DebugRequest, DebugResult, run_debug_request

__all__ = ["DebugRequest", "DebugResult", "run_debug_request"]
