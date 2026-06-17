from database.db_context import load_context
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


def build_service_event_row(extraction: dict, ctx: dict) -> dict:
    '''Takes the agent's final extractions + the DB context, and returns a service_events row dict.'''
    s2 = extraction.get("extracted_fields_section2", {})
    return {
        # 3. Foreign keys — from context, not the voice
        "individual_id": ctx["individual_id"],
        "schedule_id": ctx["schedule_id"],

        # 1. Rename / lift / copy
        "service_description": extraction["transcript"],          # renamed
        "activities_performed": extraction["activities_performed"], # copied
        "support_level": extraction["support_level"],               # copied
        "individual_response": extraction["individual_response"],   # copied
        "health_observations": s2.get("health_observations"),       # lifted
        "behavioral_observations": s2.get("behavioral_observations"),
        "community_outing": s2.get("community_outing"),

        # 2. Restructure — objects -> array of bare goal_id UUIDs
        "goals_addressed": [g["goal_id"] for g in extraction["isp_goals_addressed"]],

        # gaps we computed (A5 will formalize this column later)
        "completeness_flags": extraction.get("gaps_detected", []),

        # 4. Defaults for a finished shift
        "status": "submitted",
        "dsp_signed": True,
        # begin_time, end_time, units_calculated, confidence_score, meals,
        # personal_care, gps_* are intentionally omitted -> stay null (A5 / device / Section 3)
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
    
    # with timed("DB write (insert)"):
    #     row = build_service_event_row(section1, ctx)
    #     saved = insert_service_event(row)
        
    # print("\n Wrote service_event:", saved["event_id"])


if __name__ == "__main__":
    asyncio.run(main())