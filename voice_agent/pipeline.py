"""
pipeline.py — the reusable ClaimPilot voice-agent library.

This module holds the pure, callable pipeline functions that BOTH the local CLI
(run_pipeline.py) and the FastAPI app will import. Functions here take their
inputs as arguments (audio as raw bytes, never file paths) and RETURN results —
they never print, never read argv, never write to the DB unless that's their job.

Stage 2 adds extract() — the read + LLM path. It performs NO database writes.
"""

import json
import os
import psycopg2
import asyncio as _asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from database.db_context import load_context, insert_care_session, insert_mar_rows, insert_care_session_cur
from section_1_agent.agent import build_section1_agent
from section_1_agent.detect_gaps import detect_gaps
from section_2_agent.agent import build_section2_agent

from logging_config import get_logger, kv

log = get_logger("pipeline")

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
    async def _run():
        text = None
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content:
                text = event.content.parts[0].text
        return json.loads(text)

    return await _with_retry(_run)


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

    async def _run():
        text = None
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content:
                text = event.content.parts[0].text
        return json.loads(text)

    return await _with_retry(_run)


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


def _in_shift_window(med_time: str, shift: dict) -> bool:
    """True if a med's scheduled time falls within the shift, inclusive.
    Reuses the same window rule detect_gaps uses, so the MAR and the gap
    flags agree on which meds are administrable this shift."""
    def _t(hhmmss):
        h, m, s = (int(x) for x in hhmmss.split(":"))
        return h * 3600 + m * 60 + s
    return _t(shift["start"]) <= _t(med_time) <= _t(shift["end"])


def _build_mar_scaffold(ctx: dict, transcript: str) -> list[dict]:
    """
    Build the MAR grid the frontend displays and the DSP taps to confirm.

    - In-window meds only: a dose the DSP can't administer this shift isn't on
      the MAR (same window rule as gap detection).
    - JSON-safe and ID-free: medication_id is deliberately omitted — the client
      never sees a UUID; write_mar re-resolves it by name server-side.
    - 'mentioned_in_narration' is an advisory hint (the same transcript scan gap
      detection uses), so the frontend can nudge the DSP. Nothing is pre-confirmed:
      every dose defaults to unconfirmed and the DSP taps each one.
    """
    mentioned = any(w in (transcript or "").lower() for w in ("med", "medication", "pill"))
    scaffold = []
    for m in ctx["meds_raw"]:
        sched = str(m["scheduled_time_of_day"])
        if not _in_shift_window(sched, ctx["shift"]):
            continue
        scaffold.append({
            "medication_name": m["medication_name"],
            "dosage_amount": m["dosage_amount"],
            "administration_route": m["administration_route"],
            "scheduled_time": sched[:5],          # "07:00:00" -> "07:00"
            "was_given": None,                    # unconfirmed until the DSP taps
            "mentioned_in_narration": mentioned,  # advisory hint, not a decision
        })
    return scaffold


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
    log.info(kv(event="extract_start", medicaid_id=medicaid_id, toggles=len(toggled)))

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
    result = {
        "auto_fields": ctx["auto_fields"],
        "progress_note": section1,
        "mar_scaffold": _build_mar_scaffold(ctx, section1.get("transcript", "")),
    }
    log.info(kv(event="extract_done", medicaid_id=medicaid_id,
                activities=len(section1.get("activities_performed", [])),
                goals=len(section1.get("isp_goals_addressed", [])),
                gaps=len(section1.get("gaps_detected", [])),
                mar_meds=len(result["mar_scaffold"])))
    return result
    
    


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



def write_session(approved: dict, mar_grid: list[dict] | None = None,
                  meals: list[str] | None = None,
                  personal_care: list[str] | None = None) -> dict:
    """
    Atomically persist a whole shift: the progress note AND its MAR rows in ONE
    transaction. Either both commit or neither does — no orphan note, no orphan
    MAR rows. This is what /submit calls.

    - approved: the DSP-approved note (carries medicaid_id)
    - mar_grid: the DSP's tapped MAR confirmations
    - meals / personal_care: tap-only fields (form S10/S11), never voiced

    Returns {care_session_id, mar_rows_written}.
    """
    mar_grid = mar_grid or []
    ctx = load_context(approved["medicaid_id"])  # re-derive FKs/goal UUIDs server-side

    row = _build_care_session_row(approved, ctx)
    # Fold in the tap-only fields that don't come from voice.
    row["meals_provided"] = meals or []
    row["personal_care_activities"] = personal_care or []

    conn = psycopg2.connect(
        host=os.environ["CLOUD_SQL_HOST"], port=5432, dbname="claimpilot",
        user="postgres", password=os.environ["CLOUD_SQL_PASSWORD"], sslmode="require")
    try:
        cur = conn.cursor()
        care_session_id = insert_care_session_cur(cur, row)        # 1. note -> mints id
        log.info(kv(event="write_done", doc="PROGRESS_NOTE",
                    care_session_id=care_session_id))
        mar_count = write_mar(cur, care_session_id, approved["medicaid_id"], mar_grid)  # 2. MAR on same cursor
        log.info(kv(event="write_done", doc="MAR",
                    care_session_id=care_session_id, rows=mar_count))
        conn.commit()                                              # 3. both or neither
        log.info(kv(event="submit_committed", care_session_id=care_session_id,
                    mar_rows=mar_count))
        return {"care_session_id": care_session_id, "mar_rows_written": mar_count}
    except Exception as exc:
        conn.rollback()   # any failure -> nothing persists
        log.error(kv(event="submit_failed", medicaid_id=approved.get("medicaid_id"),
                     error=type(exc).__name__))
        raise
    finally:
        conn.close()
        
        
        
        

_RETRYABLE_MARKERS = ("RESOURCE_EXHAUSTED", "429", "quota")


def _is_quota_error(exc: Exception) -> bool:
    """True if the exception looks like a transient quota / rate-limit error.
    Matches on message text rather than a specific class, so it's robust across
    ADK/Gemini library versions."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker.lower() in text for marker in _RETRYABLE_MARKERS)


async def _with_retry(coro_factory, *, attempts: int = 3, base_delay: float = 2.0):
    """
    Run an async operation, retrying ONLY on transient quota (429) errors with
    exponential backoff. Any non-quota error raises immediately (so real bugs
    aren't masked). Gives up after `attempts` tries.

    coro_factory: a zero-arg callable returning a fresh coroutine each attempt
    (we can't re-await a spent coroutine, so we rebuild it per try).
    """
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            if not _is_quota_error(exc) or attempt == attempts:
                raise  # not retryable, or out of attempts -> surface it
            delay = base_delay * (2 ** (attempt - 1))  # 2s, 4s, 8s
            print(f"⚠  quota error (attempt {attempt}/{attempts}); retrying in {delay:.0f}s")
            await _asyncio.sleep(delay)