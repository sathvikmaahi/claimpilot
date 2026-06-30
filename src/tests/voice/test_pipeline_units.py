"""Fast unit tests for pipeline.py pure-logic helpers.

These call NO live services (no Gemini, no Cloud SQL) — they feed small fake
inputs shaped like the real data and check the output. They run in milliseconds
and cannot flake on quota or network, unlike the integration test.
"""

import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))

from services.pipeline import (
    _in_shift_window,
    _resolve_goal_ids,
    _resolve_med_id,
    _build_mar_entries,
)
from core.llm_retry import is_quota_error


# ---------------------------------------------------------------------------
# _in_shift_window — the rule that keeps out-of-shift meds off the MAR
# ---------------------------------------------------------------------------

def test_in_shift_window_includes_morning_med_on_day_shift():
    shift = {"start": "07:00:00", "end": "15:00:00"}
    assert _in_shift_window("08:00:00", shift) is True

def test_in_shift_window_excludes_evening_med_on_day_shift():
    shift = {"start": "07:00:00", "end": "15:00:00"}
    # 8PM med on a 7AM-3PM shift must NOT be administrable.
    assert _in_shift_window("20:00:00", shift) is False

def test_in_shift_window_boundary_is_inclusive():
    shift = {"start": "07:00:00", "end": "15:00:00"}
    assert _in_shift_window("07:00:00", shift) is True
    assert _in_shift_window("15:00:00", shift) is True


# ---------------------------------------------------------------------------
# _resolve_goal_ids — match model goals to REAL db UUIDs by category
# ---------------------------------------------------------------------------

def test_resolve_goal_ids_matches_by_category():
    goals_raw = [
        {"goal_id": "uuid-daily", "goal_category": "daily_living"},
        {"goal_id": "uuid-comm", "goal_category": "community_integration"},
        {"goal_id": "uuid-health", "goal_category": "health_and_safety"},
    ]
    model_goals = [
        {"category": "daily_living"},
        {"category": "community"},      # tolerant: matches community_integration
        {"category": "health_safety"},  # tolerant: matches health_and_safety
    ]
    result = _resolve_goal_ids(model_goals, goals_raw)
    assert result == ["uuid-daily", "uuid-comm", "uuid-health"]

def test_resolve_goal_ids_dedupes():
    goals_raw = [{"goal_id": "uuid-daily", "goal_category": "daily_living"}]
    model_goals = [{"category": "daily_living"}, {"category": "daily_living"}]
    # Same goal matched twice -> only one id returned.
    assert _resolve_goal_ids(model_goals, goals_raw) == ["uuid-daily"]

def test_resolve_goal_ids_empty_when_no_match():
    goals_raw = [{"goal_id": "uuid-daily", "goal_category": "daily_living"}]
    model_goals = [{"category": "employment"}]
    assert _resolve_goal_ids(model_goals, goals_raw) == []


# ---------------------------------------------------------------------------
# _resolve_med_id + _build_mar_entries — taps -> db rows, code translation
# ---------------------------------------------------------------------------

MEDS_RAW = [
    {"medication_id": "uuid-sert", "medication_name": "Sertraline"},
    {"medication_id": "uuid-met", "medication_name": "Metformin"},
]

def test_resolve_med_id_matches_by_name_case_insensitive():
    assert _resolve_med_id("sertraline", MEDS_RAW) == "uuid-sert"

def test_resolve_med_id_raises_for_unknown_med():
    import pytest
    with pytest.raises(ValueError):
        _resolve_med_id("Aspirin", MEDS_RAW)   # not on the plan

def test_build_mar_entries_given_med():
    grid = [{"medication_name": "Sertraline", "was_given": True, "admin_time": "t"}]
    entries = _build_mar_entries(grid, MEDS_RAW)
    assert entries[0]["medication_id"] == "uuid-sert"
    assert entries[0]["was_given"] is True
    assert entries[0]["reason_not_given"] is None

def test_build_mar_entries_translates_exception_code():
    grid = [{"medication_name": "Metformin", "was_given": False,
             "exception_code": "R", "note": "spat it out"}]
    entries = _build_mar_entries(grid, MEDS_RAW)
    assert entries[0]["was_given"] is False
    # "R" -> "Refused by recipient", plus the note.
    assert entries[0]["reason_not_given"] == "Refused by recipient: spat it out"


# ---------------------------------------------------------------------------
# _is_quota_error — recognize 429s, ignore real bugs
# ---------------------------------------------------------------------------

def test_is_quota_error_recognizes_resource_exhausted():
    assert is_quota_error(Exception("something RESOURCE_EXHAUSTED happened")) is True

def test_is_quota_error_recognizes_429():
    assert is_quota_error(Exception("429 Too Many Requests")) is True

def test_is_quota_error_ignores_real_bug():
    assert is_quota_error(ValueError("bad audio format")) is False


# ---------------------------------------------------------------------------
# validate_goals_resolution — every goal resolved, note required if not addressed
# ---------------------------------------------------------------------------

from services.pipeline import validate_goals_resolution, IncompleteGoals

_GOALS_RAW = [
    {"goal_id": "g1", "goal_description": "Goal One"},
    {"goal_id": "g2", "goal_description": "Goal Two"},
]

def test_goals_resolution_complete_and_valid_passes():
    resolution = [
        {"goal_id": "g1", "addressed": True, "note": ""},
        {"goal_id": "g2", "addressed": False, "note": "no opportunity"},
    ]
    validate_goals_resolution(resolution, _GOALS_RAW)  # should not raise

def test_goals_resolution_missing_goal_rejected():
    import pytest
    with pytest.raises(IncompleteGoals):
        validate_goals_resolution([{"goal_id": "g1", "addressed": True}], _GOALS_RAW)

def test_goals_resolution_not_addressed_without_note_rejected():
    import pytest
    with pytest.raises(IncompleteGoals):
        validate_goals_resolution([
            {"goal_id": "g1", "addressed": True},
            {"goal_id": "g2", "addressed": False, "note": "   "},  # blank note
        ], _GOALS_RAW)

def test_goals_resolution_not_addressed_with_note_passes():
    validate_goals_resolution([
        {"goal_id": "g1", "addressed": False, "note": "busy"},
        {"goal_id": "g2", "addressed": False, "note": "sick"},
    ], _GOALS_RAW)  # should not raise
