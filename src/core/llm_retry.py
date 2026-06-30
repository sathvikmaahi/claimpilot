"""Shared retry for transient LLM quota (429) errors.

Used by the extraction orchestrator (narrative/observation/progress_note) and the
transcription path. Retries ONLY on quota / rate-limit errors with exponential
backoff; any other error raises immediately so real bugs aren't masked.
"""

import asyncio

_RETRYABLE_MARKERS = ("RESOURCE_EXHAUSTED", "429", "quota")


def is_quota_error(exc: Exception) -> bool:
    """True if the exception looks like a transient quota / rate-limit error.
    Matches on message text rather than a class, so it's robust across
    ADK/Gemini library versions."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker.lower() in text for marker in _RETRYABLE_MARKERS)


async def with_retry(coro_factory, *, attempts: int = 3, base_delay: float = 2.0):
    """Run an async op, retrying ONLY on transient quota (429) errors with
    exponential backoff. Non-quota errors raise immediately. Gives up after
    `attempts` tries.

    coro_factory: a zero-arg callable returning a fresh coroutine each attempt
    (a spent coroutine can't be re-awaited, so we rebuild it per try).
    """
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            if not is_quota_error(exc) or attempt == attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))  # 2s, 4s, 8s
            print(f"⚠  quota error (attempt {attempt}/{attempts}); retrying in {delay:.0f}s")
            await asyncio.sleep(delay)
