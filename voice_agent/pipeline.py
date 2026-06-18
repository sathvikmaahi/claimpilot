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

from database.db_context import load_context
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