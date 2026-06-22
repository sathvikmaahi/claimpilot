"""Centralized logging setup for the ClaimPilot voice agent.

Configures structured, level-aware logging once. Every module gets its logger
via get_logger(__name__). Logs are emitted at request edges only (request in,
extract done, write done, errors) — enough to debug Cloud Run without noise.

Reused unchanged by the image pipeline fork: same observability layer.
"""

import logging
import sys

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)  # Cloud Run captures stdout
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    root = logging.getLogger("claimpilot")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger under the 'claimpilot' namespace."""
    _configure()
    return logging.getLogger(f"claimpilot.{name}")


def kv(**fields) -> str:
    """Render key=value pairs for a structured log line.
    e.g. kv(event='extract_done', goals=3) -> 'event=extract_done goals=3'."""
    return " ".join(f"{k}={v}" for k, v in fields.items())


import time
from contextlib import contextmanager


@contextmanager
def timed(label: str, logger=None):
    """Measure how long a block takes and emit it as a structured timing log.

    Usage:
        with timed("narrative_llm"):
            ...slow work...

    Logs: event=timing label=narrative_llm seconds=11.24
    Replaces the old print-based helper so timings join the structured log
    stream (visible/filterable on Cloud Run), not bare stdout.
    """
    log = logger or get_logger("timing")
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        log.info(kv(event="timing", label=label, seconds=f"{elapsed:.2f}"))
