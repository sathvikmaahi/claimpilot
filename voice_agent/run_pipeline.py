from database.db_context import load_context, insert_care_session
from section_1_agent.agent import build_section1_agent
from section_1_agent.detect_gaps import detect_gaps


import asyncio
import json

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from section_2_agent.agent import build_section2_agent

import time
from contextlib import contextmanager

@contextmanager
def timed(label):
    '''calcualted how many seconds a block of code takes, and print with the provided label'''
    start = time.perf_counter()
    yield
    print(f"⏱  {label}: {time.perf_counter() - start:.2f}s")
    
    

load_dotenv("section_1_agent/.env")   # load the .env 

APP_NAME = "claimpilot_a2"
USER_ID = "dsp_maria" # DSP profile

# Which observation toggles the DSP turned on, and the recording for each.
# "behavioral" is deliberately left out — for noe
TOGGLED = {
    "health": "/Users/shubhangvangari/Documents/AI_fellowship/care-claim-repo/care-claim-ai/voice_agent/section_2_agent/section_2_health.m4a",
    "outing": "/Users/shubhangvangari/Documents/AI_fellowship/care-claim-repo/care-claim-ai/voice_agent/section_2_agent/section_2_outing.m4a",
}

# these are the toggle options that will be presented to the DSP, in section 2
FIELD_TO_KEY = {
    "health": "health_observations",
    "behavioral": "behavioral_observations",
    "outing": "community_outing",
}


async def run_agent_on_audio(agent, audio_path, audio_mime="audio/mp4"):
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    
    #  read the auido file as raw bytes 
    #  send the audio as the input from the DSP to agent. 
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
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


async def run_section2(toggled):
    '''Instead of building one agent for the entire Section 2, on the fly spearate agents are built for each toggled feid'''
    result = {key: None for key in FIELD_TO_KEY.values()}   # everything off by default
    for field, audio_path in toggled.items():
        agent = build_section2_agent(field)                 # build the agent for THIS field
        extraction = await run_agent_on_audio(agent, audio_path)
        result[FIELD_TO_KEY[field]] = extraction["value"]
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
    return list(dict.fromkeys(resolved))   # dedupe, keep order


def build_care_session_row(extraction: dict, ctx: dict) -> dict:
    """Map the Voice Extraction Object -> a documented_care_sessions row."""
    s2 = extraction.get("extracted_fields_section2", {})

    # support_level enum differs between the agent and the DB; translate it.
    support_map = {
        "independent": "independent",
        "verbal": "verbal_prompts",
        "physical": "physical_assistance",
        "full": "full_support",
        "unknown": None,
    }

    return {
        # Foreign keys (from context, never the model)
        "shift_assignment_id": ctx["shift_assignment_id"],
        "care_recipient_id": ctx["care_recipient_id"],

        # Section 1
        "care_session_narrative": extraction["transcript"],
        "activities_performed": extraction["activities_performed"],
        "level_of_support_provided": support_map.get(extraction["support_level"]),
        "recipient_engagement_notes": extraction["individual_response"],

        # Section 2 (lifted from the nested object)
        "health_observations_notes": s2.get("health_observations"),
        "behavioral_observations_notes": s2.get("behavioral_observations"),
        "community_outing_notes": s2.get("community_outing"),

        # Goals — REAL UUIDs resolved from the DB, not the model's text
        "goals_addressed_in_session": _resolve_goal_ids(
            extraction.get("isp_goals_addressed", []), ctx["goals_raw"]
        ),

        # Gaps + confidence
        "documentation_gap_flags": [g["message"] for g in extraction.get("gaps_detected", [])],
        "ai_confidence_rating": extraction["confidence"].get("activities_performed", "Medium"),

        # Status
        "dsp_has_signed": True,
        "session_status": "submitted_by_dsp",
    }

async def main():
    # execution flow:
    # 1. Load all context from the DB in one go (for the entire pipeline, not just Section 1)
    # 2. Run Section 1 agent on the narration audio, with the goals context injected into the prompt
    # 3. Run the gap detection logic, which is fed the DB context (shift + meds) and the Section 1 extraction
    # 4. Run Section 2 agents on the toggled audios, as before
    # 5. Merge.
    
    MARCUS_MEDICAID_ID = "482910053"
    with timed("DB read (load_context)"):
        ctx = load_context(MARCUS_MEDICAID_ID)
                      # one DB read for everything

    # Section 1 — agent built with John's real goals
    with timed("Section 1  (audio + LLM)"):
        section1_agent = build_section1_agent(ctx["goals_text"])
        section1 = await run_agent_on_audio(section1_agent,  "/Users/shubhangvangari/Documents/AI_fellowship/care-claim-repo/care-claim-ai/voice_agent/section_1_agent/section1.m4a")

    # Gap detection — now fed the DB shift + meds
    section1["gaps_detected"] = detect_gaps(section1, ctx["shift"], ctx["medications"])

    # Section 2 — unchanged
    with timed("Section 2  (audio + LLM per toggle)"):
        section2 = await run_section2(TOGGLED)
        section1["extracted_fields_section2"] = section2

    print(json.dumps(section1, indent=2))
    
    
    row = build_care_session_row(section1, ctx)
    new_id = insert_care_session(row)
    print("\n Wrote care session:", new_id)
    return new_id
    

if __name__ == "__main__":
    asyncio.run(main())