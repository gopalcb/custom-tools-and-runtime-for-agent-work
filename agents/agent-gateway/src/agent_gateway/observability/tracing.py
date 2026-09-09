from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter


@contextmanager
def trace_span(name: str, attributes: dict | None = None):
    """Minimal V1 span shim; replace with OpenTelemetry without changing call sites."""
    start = perf_counter()
    span = {"name": name, "attributes": attributes or {}}
    try:
        yield span
    finally:
        span["duration_ms"] = round((perf_counter() - start) * 1000, 2)
