"""Unit tests for the progress_note_extractor (vision) agent itself.

Fast and deterministic — they validate the agent's WIRING and output CONTRACT
without a live Gemini call. The agent's live extraction behaviour is covered
separately by test_extract_image_integration.py::test_extract_image_live.
"""

import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))

from agents.progress_note_extractor.agent import (
    build_progress_note_extractor,
    ProgressNoteExtraction,
)

# Every field the vision agent must produce — identical to the voice note shape
# plus the printed-checkbox extras (meals/personal_care) and the observations.
EXPECTED_FIELDS = {
    "transcript", "activities_performed", "activity_timestamps",
    "support_level", "individual_response",
    "health_observations", "behavioral_observations", "community_outing",
    "meals", "personal_care", "isp_goals_addressed", "confidence",
}


def test_builder_returns_named_agent_with_schema():
    agent = build_progress_note_extractor("(no goals loaded)")
    assert agent.name == "progress_note_extractor"
    assert agent.output_schema is ProgressNoteExtraction


def test_builder_injects_goals_into_instruction():
    sentinel = "GOAL-SENTINEL-12345"
    agent = build_progress_note_extractor(sentinel)
    # the recipient's goals must be substituted into the prompt...
    assert sentinel in agent.instruction
    # ...and the placeholder must not be left un-filled.
    assert "{goals_text}" not in agent.instruction


def test_extraction_schema_has_all_form_fields():
    assert set(ProgressNoteExtraction.model_fields) == EXPECTED_FIELDS


def test_blank_form_fields_default_to_null_or_empty():
    """A blank section means 'not filled': observations default to None and the
    checkbox lists default to empty, so the agent is never forced to invent."""
    note = ProgressNoteExtraction(
        transcript="", activities_performed=[], activity_timestamps=[],
        support_level="unknown", individual_response="", isp_goals_addressed=[],
        confidence={"activities_performed": 0.0, "activity_timestamps": 0.0,
                    "support_level": 0.0, "individual_response": 0.0},
    )
    assert note.health_observations is None
    assert note.behavioral_observations is None
    assert note.community_outing is None
    assert note.meals == [] and note.personal_care == []
