"""Integration test for /transcribe — audio in, faithful text out.

Marked integration: calls live Gemini. Uses a short real clip and asserts a
non-empty transcript comes back (exact wording varies, so we check substance,
not an exact string).
"""

import os
import sys
import asyncio
import pytest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, ".."))

from pipeline import transcribe

# Adjust if your test clip lives elsewhere.
CLIP = os.path.join(here, "..", "..", "transcript_test.m4a")


@pytest.mark.integration
def test_transcribe_returns_text():
    with open(CLIP, "rb") as f:
        audio = f.read()
    transcript = asyncio.run(transcribe(audio))
    assert isinstance(transcript, str)
    assert len(transcript.strip()) > 5, "expected a non-trivial transcript"
    print(f"  transcript: {transcript}")
