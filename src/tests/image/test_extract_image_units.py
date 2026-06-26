"""Fast unit tests for the image read path (extract_image).

These mock the three externals — load_context (DB), upload_progress_note_pages
(GCS), and _run_progress_note (Gemini) — so they call NO live services and run
in milliseconds. They lock the contract: the response blocks, the progress_note
shape matching voice, the S2/meals/personal_care split, and the graceful
degraded path.
"""

import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))

import pytest
import services.pipeline as pipeline


# A context shaped like load_context()'s return, but empty where it can be so
# the helpers (_build_mar_scaffold/_build_active_goals) produce empty results.
FAKE_CTX = {
    "auto_fields": {"recipient_name": "Test Recipient", "medicaid_id": "X"},
    "meds_raw": [], "goals_raw": [], "medications": [],
    "shift": {"start": "07:00:00", "end": "15:00:00"}, "goals_text": "(none)",
}

# A full agent output (every field the schema produces).
FULL_EXTRACTION = {
    "transcript": "t", "activities_performed": ["a"], "activity_timestamps": [],
    "support_level": "verbal", "individual_response": "r",
    "health_observations": "h", "behavioral_observations": "b", "community_outing": "c",
    "meals": ["Lunch"], "personal_care": ["Bathing"], "isp_goals_addressed": [],
    "confidence": {"activities_performed": 0.9, "activity_timestamps": 1.0,
                   "support_level": 0.8, "individual_response": 0.9},
}

PAGES = [(b"x", "image/jpeg"), (b"y", "image/jpeg")]

# The exact keys a progress_note must carry — identical to the voice shape so
# /submit consumes either pipeline's output unchanged.
PROGRESS_NOTE_KEYS = {
    "transcript", "activities_performed", "activity_timestamps", "support_level",
    "individual_response", "isp_goals_addressed", "confidence",
    "gaps_detected", "extracted_fields_section2",
}
TOP_LEVEL_KEYS = {
    "auto_fields", "progress_note", "mar_scaffold", "active_goals",
    "meals", "personal_care", "source_image_uris", "extraction_failed",
}


@pytest.fixture
def patched(monkeypatch):
    """Mock the DB read + GCS upload so only the assembly logic is exercised."""
    monkeypatch.setattr(pipeline, "load_context", lambda mid: FAKE_CTX)
    monkeypatch.setattr(
        pipeline, "upload_progress_note_pages",
        lambda mid, date, pages: {"upload_id": "u1", "uris": ["gs://b/p1.jpg", "gs://b/p2.jpg"]},
    )


async def _ok_agent(goals_text, pages):
    return dict(FULL_EXTRACTION)


async def _boom_agent(goals_text, pages):
    raise RuntimeError("simulated vision failure")


async def test_happy_returns_expected_blocks_and_voice_shape(patched, monkeypatch):
    monkeypatch.setattr(pipeline, "_run_progress_note", _ok_agent)
    res = await pipeline.extract_image("X", PAGES)

    assert set(res) == TOP_LEVEL_KEYS
    assert res["extraction_failed"] is False
    # progress_note is byte-identical to the voice shape.
    assert set(res["progress_note"]) == PROGRESS_NOTE_KEYS


async def test_happy_splits_observations_and_taps(patched, monkeypatch):
    monkeypatch.setattr(pipeline, "_run_progress_note", _ok_agent)
    res = await pipeline.extract_image("X", PAGES)

    # S7/8/9 fold into extracted_fields_section2 (the contract key).
    assert res["progress_note"]["extracted_fields_section2"] == {
        "health_observations": "h", "behavioral_observations": "b", "community_outing": "c",
    }
    # meals/personal_care ride OUTSIDE progress_note (they go to /submit top-level).
    assert res["meals"] == ["Lunch"]
    assert res["personal_care"] == ["Bathing"]
    assert "meals" not in res["progress_note"]
    assert res["source_image_uris"] == ["gs://b/p1.jpg", "gs://b/p2.jpg"]


async def test_degraded_on_agent_failure_keeps_saved_pages(patched, monkeypatch):
    monkeypatch.setattr(pipeline, "_run_progress_note", _boom_agent)
    res = await pipeline.extract_image("X", PAGES)

    assert res["extraction_failed"] is True
    # The pages are already saved, so the URIs survive — nothing is lost.
    assert res["source_image_uris"] == ["gs://b/p1.jpg", "gs://b/p2.jpg"]
    # The note is an empty-but-valid skeleton with the SAME keys as a real note.
    assert set(res["progress_note"]) == PROGRESS_NOTE_KEYS
    assert res["progress_note"]["transcript"] == ""
    assert res["meals"] == [] and res["personal_care"] == []
