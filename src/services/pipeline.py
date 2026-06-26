"""
pipeline.py — the reusable ClaimPilot voice-agent library.

This module holds the pure, callable pipeline functions that BOTH the local CLI
(run_pipeline.py) and the FastAPI app will import. Functions here take their
inputs as arguments (audio as raw bytes, never file paths) and RETURN results —
they never print, never read argv, never write to the DB unless that's their job.

Stage 2 adds extract() — the read + LLM path. It performs NO database writes.
"""

import json
import asyncio as _asyncio
import datetime as _dt

from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.agents.llm_agent import Agent


from db.db_context import load_context, create_care_session, insert_mar_rows
from db.voice_session import get_session
from agents.narrative_extractor.agent import build_narrative_extractor
from agents.narrative_extractor.detect_gaps import detect_gaps
from agents.observation_extractor.agent import build_observation_extractor
from agents.progress_note_extractor.agent import build_progress_note_extractor
from infra.storage import upload_progress_note_pages, promote_to_permanent

from core.observability import get_logger, kv, timed

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
    agent = build_narrative_extractor(goals_text)
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
        agent = build_observation_extractor(field)  # build the agent for THIS field
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
    with timed("narrative_llm", logger=log):
        section1 = await _run_section1(
            ctx["goals_text"], narration_activities, narration_engagement
        )

    # 3. Gap detection — deterministic Python, fed the DB shift + meds.
    section1["gaps_detected"] = detect_gaps(section1, ctx["shift"], ctx["medications"])

    # 4. Section 2 — one narrow agent per toggle.
    with timed("observation_llm", logger=log):
        section1["extracted_fields_section2"] = await _run_section2(toggled)

    # 5. Assemble the response blocks. progress_note is the whole Section 1 object.
    result = {
        "auto_fields": ctx["auto_fields"],
        "progress_note": section1,
        "mar_scaffold": _build_mar_scaffold(ctx, section1.get("transcript", "")),
        "active_goals": _build_active_goals(ctx, section1.get("isp_goals_addressed", [])),
    }
    
    log.info(kv(event="extract_done", medicaid_id=medicaid_id,
                activities=len(section1.get("activities_performed", [])),
                goals=len(section1.get("isp_goals_addressed", [])),
                gaps=len(section1.get("gaps_detected", [])),
                mar_meds=len(result["mar_scaffold"])))
    return result


async def _run_progress_note(goals_text: str, pages: list[tuple[bytes, str]]) -> dict:
    """Run the single Progress Note vision agent over ALL page images at once.

    `pages` is an ordered list of (image_bytes, mime_type) — page 1 first. They
    are fed to ONE agent call as ordered image parts (the multi-page form is one
    document), exactly as _run_section1 feeds two audio clips to one agent.
    """
    agent = build_progress_note_extractor(goals_text)
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in pages]
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


def _degraded_result(ctx: dict, stored: dict) -> dict:
    """Build a usable review screen when extraction fails AFTER the pages are
    saved (option A). The DB-derived blocks (header, MAR, goals) are intact; the
    note is an empty but structurally-valid skeleton the DSP fills in manually.
    extraction_failed=True tells the frontend to prompt for manual entry.
    """
    empty_note = {
        "transcript": "",
        "activities_performed": [],
        "activity_timestamps": [],
        "support_level": "unknown",
        "individual_response": "",
        "isp_goals_addressed": [],
        "confidence": {
            "activities_performed": 0.0,
            "activity_timestamps": 0.0,
            "support_level": 0.0,
            "individual_response": 0.0,
        },
        "gaps_detected": [],
        "extracted_fields_section2": {
            "health_observations": None,
            "behavioral_observations": None,
            "community_outing": None,
        },
    }
    return {
        "auto_fields": ctx["auto_fields"],
        "progress_note": empty_note,
        "mar_scaffold": _build_mar_scaffold(ctx, ""),
        "active_goals": _build_active_goals(ctx, []),
        "meals": [],
        "personal_care": [],
        "source_image_uris": stored["uris"],
        "extraction_failed": True,
    }


async def extract_image(medicaid_id: str, pages: list[tuple[bytes, str]]) -> dict:
    """The image READ path. Loads context, persists the source pages to GCS,
    runs the one vision agent, detects gaps, assembles the result. Performs NO
    database writes (the care-session write still happens later via /submit).

    Mirrors extract() so the frontend renders the SAME review form: returns the
    same four blocks (auto_fields, progress_note, mar_scaffold, active_goals)
    plus meals/personal_care (pre-filled from the form's S10/S11 checkboxes) and
    source_image_uris (the stored pages, for linkage at /submit).
    """
    log.info(kv(event="extract_image_start", medicaid_id=medicaid_id, pages=len(pages)))

    # 1. One DB read for everything both documents need (header, goals, meds, shift).
    ctx = load_context(medicaid_id)

    # 2. Persist the source pages FIRST, so the original paper form is retained
    #    even if extraction later fails. The shift is today's (DB filters current_date).
    shift_date = _dt.date.today().isoformat()
    stored = upload_progress_note_pages(medicaid_id, shift_date, pages)

    # 3. One vision agent reads ALL pages -> the Section-1/2 note shape. If the
    #    read fails, the pages are already saved, so degrade to a manual-entry
    #    shell instead of blocking the DSP (option A).
    try:
        with timed("progress_note_llm", logger=log):
            extraction = await _run_progress_note(ctx["goals_text"], pages)
    except Exception as exc:
        log.warning(kv(event="extract_image_degraded", medicaid_id=medicaid_id,
                       error=type(exc).__name__))
        return _degraded_result(ctx, stored)

    # 4. Split the agent output: the Section 2 observations + the tap-style
    #    meals/personal_care ride OUTSIDE progress_note (matching the voice shape),
    #    everything else IS the progress_note (same fields as narrative_extractor).
    section2 = {
        "health_observations": extraction.pop("health_observations", None),
        "behavioral_observations": extraction.pop("behavioral_observations", None),
        "community_outing": extraction.pop("community_outing", None),
    }
    meals = extraction.pop("meals", []) or []
    personal_care = extraction.pop("personal_care", []) or []
    section1 = extraction

    # 5. Gap detection — the same deterministic Python the voice path uses.
    section1["gaps_detected"] = detect_gaps(section1, ctx["shift"], ctx["medications"])

    # 6. Fold observations into the contract key the frontend + /submit expect.
    section1["extracted_fields_section2"] = section2

    # 7. Assemble — the four voice blocks, plus meals/personal_care + stored URIs.
    result = {
        "auto_fields": ctx["auto_fields"],
        "progress_note": section1,
        "mar_scaffold": _build_mar_scaffold(ctx, section1.get("transcript", "")),
        "active_goals": _build_active_goals(ctx, section1.get("isp_goals_addressed", [])),
        "meals": meals,
        "personal_care": personal_care,
        "source_image_uris": stored["uris"],
        "extraction_failed": False,
    }

    log.info(kv(event="extract_image_done", medicaid_id=medicaid_id,
                activities=len(section1.get("activities_performed", [])),
                goals=len(section1.get("isp_goals_addressed", [])),
                gaps=len(section1.get("gaps_detected", [])),
                mar_meds=len(result["mar_scaffold"]),
                pages=len(stored["uris"])))
    return result


def _build_active_goals(ctx: dict, matched_goals: list) -> list[dict]:
    """Build the full active-goal list for the frontend's resolution checklist.

    Returns EVERY active goal (not just AI-matched ones), so the DSP can
    consciously resolve each. Goals the AI matched from the narration are
    flagged ai_matched=True so the frontend can pre-check them; the DSP must
    still resolve the rest. JSON-safe: goal_id is stringified.
    """
    # The categories the AI matched (its category labels, lowercased).
    matched_cats = {(g.get("category") or "").lower() for g in matched_goals}

    goals = []
    for g in ctx["goals_raw"]:
        real_cat = g["goal_category"].lower()
        # ai_matched if any AI category prefix-matches this real category
        # (same tolerant rule _resolve_goal_ids uses).
        ai_matched = any(
            real_cat.startswith(mc[:6]) or mc[:6] in real_cat
            for mc in matched_cats if mc
        )
        goals.append({
            "goal_id": str(g["goal_id"]),
            "category": g["goal_category"],
            "description": g["goal_description"],
            "ai_matched": ai_matched,
        })
    return goals

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

class IncompleteGoals(Exception):
    """Raised when the DSP's goal resolution doesn't cover every active goal,
    or a not-addressed goal lacks the required note. A submission cannot be
    saved until every goal is consciously resolved."""


def validate_goals_resolution(goals_resolution: list[dict], goals_raw: list) -> None:
    """Enforce that every active goal is consciously resolved.

    Rules:
      1. Every active goal must appear in goals_resolution (addressed true/false).
      2. A goal marked addressed=False must carry a non-empty note.

    Raises IncompleteGoals with a specific message if either rule is violated.
    Pure function: no DB, no side effects — just policy.
    """
    resolution = goals_resolution or []

    # Index the resolution by goal_id for lookup.
    by_id = {str(r.get("goal_id")): r for r in resolution}

    for g in goals_raw:
        gid = str(g["goal_id"])
        desc = g.get("goal_description", gid)

        # Rule 1: every active goal must be resolved.
        if gid not in by_id:
            raise IncompleteGoals(
                f"Goal not resolved: '{desc}'. Every goal must be marked "
                "addressed or not addressed before submitting."
            )

        entry = by_id[gid]
        if "addressed" not in entry:
            raise IncompleteGoals(
                f"Goal '{desc}' has no addressed decision (true/false)."
            )

        # Rule 2: not-addressed goals require a note.
        if not entry["addressed"] and not (entry.get("note") or "").strip():
            raise IncompleteGoals(
                f"Goal '{desc}' is marked not addressed but has no note. "
                "A reason is required when a goal is not addressed."
            )
            
            
def _confidence_value(score) -> str | None:
    """Render the agent's 0.0-1.0 confidence for the record (stored as text, e.g. "0.85").

    The agents now emit a numeric confidence (0.0-1.0). We persist the raw score.
    The old High/Medium/Low CHECK constraint on ai_confidence_rating has been
    dropped (see schema.sql) to allow this. Returns None if no score is present.
    """
    if score is None:
        return None
    try:
        return f"{float(score):.2f}"
    except (TypeError, ValueError):
        return None


def _build_care_session_row(approved: dict, ctx: dict, goals_resolution: list[dict] | None = None) -> dict:
    """Map the approved note (Voice Extraction Object) -> a documented_care_sessions row."""
    goals_resolution = goals_resolution or []
    s2 = approved.get("extracted_fields_section2", {}) or {}

    # support_level enum differs between the agent and the DB; translate it.
    support_map = {
        "independent": "independent",
        "verbal": "verbal_prompts",
        "physical": "physical_assistance",
        "full": "full_support",
        "unknown": None,
    }

    # The DSP's resolution is authoritative for which goals were addressed.
    # Derive the flat uuid[] (addressed subset) from it, validating each id
    # against the recipient's real active goals (never trust a client id blindly).
    valid_goal_ids = {str(g["goal_id"]) for g in ctx["goals_raw"]}
    addressed_ids = [
        r["goal_id"] for r in goals_resolution
        if r.get("addressed") and str(r.get("goal_id")) in valid_goal_ids
    ]

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
        # Goals — addressed subset now comes from the DSP's resolution, not the AI match.
        "goals_addressed_in_session": addressed_ids,
        # Full per-goal decision (addressed yes/no + note) stored as jsonb.
        "goals_resolution": goals_resolution,
        # Gaps + confidence.
        "documentation_gap_flags": [g["message"] for g in approved.get("gaps_detected", [])],
        "ai_confidence_rating": _confidence_value(approved.get("confidence", {}).get("activities_performed")),
        # Status — the DSP has reviewed and signed.
        "dsp_has_signed": True,
        "session_status": "submitted_by_dsp",
    }

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


def write_mar(session, care_session_id: str, medicaid_id: str, mar_grid: list[dict]) -> int:
    """
    Write the approved MAR grid as medication_administration_records rows.

    Re-derives meds_raw (real medication_ids) from the DB, resolves each grid
    entry's UUID by name server-side, translates exception codes into stored
    reasons, and inserts via insert_mar_rows on the caller's ORM session (shared
    transaction with the progress note). Returns the row count.
    """
    ctx = load_context(medicaid_id)
    entries = _build_mar_entries(mar_grid, ctx["meds_raw"])
    return insert_mar_rows(session, care_session_id, entries)



def write_session(approved: dict, mar_grid: list[dict] | None = None,
                  meals: list[str] | None = None,
                  personal_care: list[str] | None = None,
                  goals_resolution: list[dict] | None = None,
                  source_image_uris: list[str] | None = None) -> dict:
    
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
    # Enforce complete goal resolution BEFORE opening the write transaction.
    validate_goals_resolution(goals_resolution or [], ctx["goals_raw"])

    row = _build_care_session_row(approved, ctx, goals_resolution or [])
    # Fold in the tap-only fields that don't come from voice.
    row["meals_provided"] = meals or []
    row["personal_care_activities"] = personal_care or []
    # Link the source photos when the note came from the image pipeline. On
    # submit they are promoted out of TTL-expiring staging into permanent
    # storage; the row stores those durable URIs. Voice submits send none -> NULL.
    row["source_image_uris"] = promote_to_permanent(source_image_uris) if source_image_uris else None

    # One ORM session == one transaction. create_care_session + write_mar both
    # run on it; session.commit() persists both. If anything raises, the `with`
    # exit closes the session and the uncommitted transaction rolls back —
    # so it's still note + MAR together or neither.
    try:
        with get_session() as session:
            care_session_id = create_care_session(session, row)    # 1. note -> mints id
            log.info(kv(event="write_done", doc="PROGRESS_NOTE",
                        care_session_id=care_session_id))
            mar_count = write_mar(session, care_session_id, approved["medicaid_id"], mar_grid)  # 2. MAR in same session
            log.info(kv(event="write_done", doc="MAR",
                        care_session_id=care_session_id, rows=mar_count))
            session.commit()                                       # 3. both or neither
        log.info(kv(event="submit_committed", care_session_id=care_session_id,
                    mar_rows=mar_count))
        return {"care_session_id": care_session_id, "mar_rows_written": mar_count}
    except Exception as exc:
        log.error(kv(event="submit_failed", medicaid_id=approved.get("medicaid_id"),
                     error=type(exc).__name__))
        raise
        
        
        
        

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
            
            
            
# TRANSCRIPTION — (/transcribe)
# ---------------------------------------------------------------------------
# A stateless, write-free speech->text service. Used by the frontend for voice
# notes (e.g. per-goal notes): audio in, plain text out. NO DB, no goals, no
# extraction schema. The text reaches the DB only later, via /submit inside
# goals_resolution — /transcribe itself saves nothing.


def _build_transcription_agent() -> Agent:
    """A schema-less agent that faithfully transcribes spoken audio to text.

    Unlike the extractor agents, it returns PLAIN TEXT (no Pydantic schema) and
    is told NOT to interpret, structure, or embellish — only to write down what
    was said, lightly cleaning filler. Faithfulness matters: this can become a
    clinical note supporting Medicaid billing, so no invented content.
    """
    return Agent(
        model="gemini-2.5-flash",
        name="transcription_agent",
        description="Faithfully transcribes a short spoken note to text.",
        instruction=(
            "You are a transcription service. The user's message is spoken audio. "
            "Write down exactly what was said, as clean readable text. "
            "Lightly remove filler words and false starts (um, uh, repeated words), "
            "but do NOT add, omit, summarize, interpret, or rephrase the content. "
            "Return only the transcribed text — no preamble, no labels, no commentary."
        ),
        # NOTE: no output_schema — this agent returns plain text, not JSON.
    )


# Build once and reuse (the agent is identical for every note).
_transcription_agent = _build_transcription_agent()


async def transcribe(audio_bytes: bytes, audio_mime: str = "audio/mp4") -> str:
    """Transcribe one audio clip to plain text. Stateless, no DB writes.

    Reuses the same runner machinery as the extractors but, because the agent
    is schema-less, reads the text directly (no json.loads). Wrapped in the
    429 retry so a transient quota error retries like extraction does.
    """
    log.info(kv(event="transcribe_start", bytes=len(audio_bytes)))
    runner = InMemoryRunner(agent=_transcription_agent, app_name=APP_NAME)
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
        return text

    transcript = await _with_retry(_run)
    log.info(kv(event="transcribe_done", chars=len(transcript or "")))
    return (transcript or "").strip()