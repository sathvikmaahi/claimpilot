"""
pipeline.py — the reusable ClaimPilot voice-agent library.

This module holds the pure, callable pipeline functions that BOTH the local CLI
(run_pipeline.py) and the FastAPI app will import. Functions here take their
inputs as arguments (audio as raw bytes, never file paths) and RETURN results —
they never print, never read argv, never write to the DB unless that's their job.

Stage 2 adds extract() — the read + LLM path. It performs NO database writes.
"""

import json

from google.adk.runners import InMemoryRunner
from google.genai import types

from database.db_context import load_context, insert_care_session, insert_mar_rows
from section_1_agent.agent import build_section1_agent
from section_1_agent.detect_gaps import detect_gaps
from section_2_agent.agent import build_section2_agent


APP_NAME = "claimpilot_a2"
USER_ID = "dsp_maria"  # DSP profile (single-user POC)

# Maps a DSP-facing observation toggle -> the key it lands on in the result.
# Untoggled observations stay None (no agent call for them).
FIELD_TO_KEY = {
    "health": "health_observations",
    "behavioral": "behavioral_observations",
    "outing": "community_outing",
}


async def _run_agent_on_audio(agent, audio_bytes: bytes, audio_mime: str = "audio/mp4") -> dict:
    """
    Run one ADK agent over one audio clip (raw bytes) and return its parsed JSON.

    Takes BYTES, not a path: the API receives uploaded bytes with no file on disk,
    and the CLI reads its own files and hands the bytes in. One function, two callers.
    """
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime)],
    )
    text = None
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content:
            text = event.content.parts[0].text
    return json.loads(text)


async def _run_section1(goals_text: str, narration_activities: bytes,
                        narration_engagement: bytes | None = None) -> dict:
    """
    Run the Section 1 agent over the narration.

    The DSP speaks in two guided prompts — WHAT they did (narration_activities)
    and HOW the individual responded (narration_engagement). Both clips feed the
    SAME verified Section 1 agent in one call; it separates them into the right
    fields itself (activities_performed vs individual_response). The second clip
    is optional: a single combined recording (engagement=None) is fully supported,
    because the agent extracts both signals from whatever audio it's given.
    """
    agent = build_section1_agent(goals_text)
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    parts = [types.Part.from_bytes(data=narration_activities, mime_type="audio/mp4")]
    if narration_engagement is not None:
        parts.append(types.Part.from_bytes(data=narration_engagement, mime_type="audio/mp4"))

    message = types.Content(role="user", parts=parts)
    text = None
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content:
            text = event.content.parts[0].text
    return json.loads(text)


async def _run_section2(toggled: dict[str, bytes]) -> dict:
    """
    Run one narrow Section 2 agent per toggled observation.

    `toggled` maps field name ("health"/"behavioral"/"outing") -> that clip's bytes.
    Untoggled fields are absent from the dict and stay None in the result.
    """
    result = {key: None for key in FIELD_TO_KEY.values()}  # everything off by default
    for field, audio_bytes in toggled.items():
        agent = build_section2_agent(field)  # build the agent for THIS field
        extraction = await _run_agent_on_audio(agent, audio_bytes)
        result[FIELD_TO_KEY[field]] = extraction["value"]
    return result


def _build_mar_scaffold(ctx: dict) -> list[dict]:
    """
    Placeholder for the MAR scaffold (fully populated in Stage 3, Commit 7).

    For now returns an empty list so extract()'s return SHAPE is stable — the
    'mar_scaffold' key always exists, callers can rely on it, and Commit 7 only
    has to fill it in (shift-window filtering + 'mentioned' hint) without changing
    the contract.
    """
    return []


async def extract(medicaid_id: str,
                  narration_activities: bytes,
                  narration_engagement: bytes | None = None,
                  toggled: dict[str, bytes] | None = None) -> dict:
    """
    The READ path. Loads context, runs the agents, detects gaps, assembles the
    result. Performs NO database writes.

    Returns three clearly-separated blocks:
      - auto_fields:    header the form pre-fills but the DSP never speaks
      - progress_note:  the LLM-authored voice extraction (the editable note)
      - mar_scaffold:   the DB-prefilled med grid the DSP taps to confirm (Stage 3)
    """
    toggled = toggled or {}

    # 1. One DB read for everything both documents need.
    ctx = load_context(medicaid_id)

    # 2. Section 1 — WHAT + HOW into the verified agent.
    section1 = await _run_section1(
        ctx["goals_text"], narration_activities, narration_engagement
    )

    # 3. Gap detection — deterministic Python, fed the DB shift + meds.
    section1["gaps_detected"] = detect_gaps(section1, ctx["shift"], ctx["medications"])

    # 4. Section 2 — one narrow agent per toggle.
    section1["extracted_fields_section2"] = await _run_section2(toggled)

    # 5. Assemble the three blocks. progress_note is the whole Section 1 object.
    return {
        "auto_fields": ctx["auto_fields"],
        "progress_note": section1,
        "mar_scaffold": _build_mar_scaffold(ctx),
    }
    
    


def _resolve_goal_ids(model_goals, goals_raw):
    """
    Turn the model's matched goals into REAL goal_id UUIDs from the database.
    Trust the model for WHICH goals (by category), never for the UUID itself.
    """
    resolved = []
    for mg in model_goals:
        model_cat = (mg.get("category") or "").lower()
        for real in goals_raw:
            real_cat = real["goal_category"].lower()
            # tolerant match: "community" matches "community_integration",
            # "health_safety" matches "health_and_safety", etc.
            if real_cat.startswith(model_cat[:6]) or model_cat[:6] in real_cat:
                resolved.append(real["goal_id"])
                break
    return list(dict.fromkeys(resolved))  # dedupe, keep order


def _build_care_session_row(approved: dict, ctx: dict) -> dict:
    """Map the approved note (Voice Extraction Object) -> a documented_care_sessions row."""
    s2 = approved.get("extracted_fields_section2", {}) or {}

    # support_level enum differs between the agent and the DB; translate it.
    support_map = {
        "independent": "independent",
        "verbal": "verbal_prompts",
        "physical": "physical_assistance",
        "full": "full_support",
        "unknown": None,
    }

    return {
        # Foreign keys — re-derived from the DB, never from the client.
        "shift_assignment_id": ctx["shift_assignment_id"],
        "care_recipient_id": ctx["care_recipient_id"],

        # Section 1 content (DSP may have edited these on screen).
        "care_session_narrative": approved["transcript"],
        "activities_performed": approved["activities_performed"],
        "level_of_support_provided": support_map.get(approved["support_level"]),
        "recipient_engagement_notes": approved["individual_response"],

        # Section 2 observations.
        "health_observations_notes": s2.get("health_observations"),
        "behavioral_observations_notes": s2.get("behavioral_observations"),
        "community_outing_notes": s2.get("community_outing"),

        # Goals — REAL UUIDs resolved from the DB by category, not the model's text.
        "goals_addressed_in_session": _resolve_goal_ids(
            approved.get("isp_goals_addressed", []), ctx["goals_raw"]
        ),

        # Gaps + confidence.
        "documentation_gap_flags": [g["message"] for g in approved.get("gaps_detected", [])],
        "ai_confidence_rating": approved.get("confidence", {}).get("activities_performed", "Medium"),

        # Status — the DSP has reviewed and signed.
        "dsp_has_signed": True,
        "session_status": "submitted_by_dsp",
    }


def write_progress_note(approved: dict) -> str:
    """
    The WRITE path for the progress note. Takes the DSP-approved note data
    (carrying medicaid_id), re-derives foreign keys and goal UUIDs from the DB,
    writes one documented_care_sessions row, and returns the new care_session_id.
    """
    ctx = load_context(approved["medicaid_id"])  # re-derive trustworthy values server-side
    row = _build_care_session_row(approved, ctx)
    return insert_care_session(row)


# MAR exception codes (from the paper form) -> human-readable reason prefix.
# The DB stores a free-text reason_if_not_given; the UI uses these short codes.
_EXCEPTION_LABELS = {
    "R": "Refused by recipient",
    "O": "Omitted",
    "H": "Hospitalized",
    "SA": "Self-administered",
}


def _resolve_med_id(med_name: str, meds_raw: list) -> str:
    """
    Resolve a MAR entry's REAL medication_id from the DB by matching name.
    Trust the client for WHICH med (by name) and what happened, never the UUID.
    """
    target = (med_name or "").strip().lower()
    for real in meds_raw:
        if real["medication_name"].strip().lower() == target:
            return real["medication_id"]
    raise ValueError(f"MAR entry names a medication not on this recipient's plan: {med_name!r}")


def _build_mar_entries(mar_grid: list[dict], meds_raw: list) -> list[dict]:
    """
    Turn the DSP's tapped MAR grid into the rows insert_mar_rows expects.

    Each grid item:
      - medication_name  (what the DSP saw and tapped)
      - was_given        (bool)
      - admin_time       (timestamp, when given)
      - exception_code   ("R"/"O"/"H"/"SA", only when not given)
      - note             (optional free-text added to the reason)
    """
    entries = []
    for item in mar_grid:
        med_id = _resolve_med_id(item["medication_name"], meds_raw)
        if item["was_given"]:
            entries.append({
                "medication_id": med_id,
                "was_given": True,
                "admin_time": item.get("admin_time"),
                "reason_not_given": None,
            })
        else:
            # Compose the stored reason from the exception code + optional note.
            code = item.get("exception_code")
            label = _EXCEPTION_LABELS.get(code, code or "Not given")
            note = item.get("note")
            reason = f"{label}: {note}" if note else label
            entries.append({
                "medication_id": med_id,
                "was_given": False,
                "admin_time": None,
                "reason_not_given": reason,
            })
    return entries


def write_mar(cur, care_session_id: str, medicaid_id: str, mar_grid: list[dict]) -> int:
    """
    Write the approved MAR grid as medication_administration_records rows.

    Re-derives meds_raw (real medication_ids) from the DB, resolves each grid
    entry's UUID by name server-side, translates exception codes into stored
    reasons, and inserts via insert_mar_rows on the caller's cursor (shared
    transaction with the progress note). Returns the row count.
    """
    ctx = load_context(medicaid_id)
    entries = _build_mar_entries(mar_grid, ctx["meds_raw"])
    return insert_mar_rows(cur, care_session_id, entries)