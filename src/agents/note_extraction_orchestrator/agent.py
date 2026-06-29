"""note_extraction_orchestrator — the root agent for shift-note extraction.

A deterministic ADK BaseAgent (no LLM of its own). Given the prepared inputs in
session state, it routes by input modality:

  - VOICE  -> narrative_extractor + one observation_extractor per toggled section,
              run CONCURRENTLY (independent calls, so no reason to serialize).
  - IMAGE  -> progress_note_extractor (single call over the page images).

The deterministic glue (DB read, GCS storage, gap detection, MAR scaffold, goal
list, assembly, the write) stays in services/pipeline.py AROUND this agent — the
root orchestrates agents only, never DB/GCS side effects.

Contract: the driver seeds ctx.session.state['extraction_input'] = {modality, ...}
and reads the extracted note back as JSON from the orchestrator's final event:
  - voice -> {"section1": <narrative>, "section2": {health/behavioral/community}}
  - image -> {"note": <progress note>}
"""

import asyncio
import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.narrative_extractor.agent import build_narrative_extractor, narrative_extractor
from agents.observation_extractor.agent import build_observation_extractor, observation_extractor
from agents.progress_note_extractor.agent import build_progress_note_extractor, progress_note_extractor
from core.llm_retry import with_retry

APP_NAME = "claimpilot_a2"
USER_ID = "dsp_maria"  # DSP profile (single-user POC)

# DSP-facing observation toggle -> the key it lands on in the result.
FIELD_TO_KEY = {
    "health": "health_observations",
    "behavioral": "behavioral_observations",
    "outing": "community_outing",
}


# --- per-agent execution (one fresh runner + session per call, with 429 retry) ---

async def _run_agent_over_parts(agent, parts: list) -> dict:
    """Run one agent over a fresh session with the given content parts -> parsed JSON."""
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    message = types.Content(role="user", parts=parts)

    async def _run():
        text = None
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content:
                text = event.content.parts[0].text
        return json.loads(text)

    return await with_retry(_run)


async def _run_narrative(goals_text: str, narration_activities: bytes,
                         narration_engagement: bytes | None = None) -> dict:
    """Section 1: the DSP's WHAT + HOW clips feed the one narrative agent."""
    parts = [types.Part.from_bytes(data=narration_activities, mime_type="audio/mp4")]
    if narration_engagement is not None:
        parts.append(types.Part.from_bytes(data=narration_engagement, mime_type="audio/mp4"))
    return await _run_agent_over_parts(build_narrative_extractor(goals_text), parts)


async def _run_observation(field: str, audio_bytes: bytes) -> tuple[str, str]:
    """Section 2: one narrow agent for ONE toggled observation. Returns (key, value)."""
    agent = build_observation_extractor(field)
    extraction = await _run_agent_over_parts(
        agent, [types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp4")]
    )
    return FIELD_TO_KEY[field], extraction["value"]


async def _run_progress_note(goals_text: str, pages: list[tuple[bytes, str]]) -> dict:
    """Image: the one vision agent reads ALL page images in a single call."""
    parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in pages]
    return await _run_agent_over_parts(build_progress_note_extractor(goals_text), parts)


# --- modality branches ---

async def _extract_voice(inp: dict) -> dict:
    """Narrative + each toggled observation, run CONCURRENTLY (the streamline).

    The calls are independent (none reads another's output), so they fan out
    together: latency becomes the slowest single call, not the sum.
    """
    toggled = inp.get("toggled") or {}
    narrative, *observations = await asyncio.gather(
        _run_narrative(inp["goals_text"], inp["narration_activities"], inp.get("narration_engagement")),
        *(_run_observation(field, audio) for field, audio in toggled.items()),
    )
    section2 = {key: None for key in FIELD_TO_KEY.values()}  # untoggled stay None
    for key, value in observations:
        section2[key] = value
    return {"section1": narrative, "section2": section2}


async def _extract_image(inp: dict) -> dict:
    return {"note": await _run_progress_note(inp["goals_text"], inp["pages"])}


class NoteExtractionOrchestrator(BaseAgent):
    """Deterministic root that routes extraction by modality (no LLM of its own)."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        inp = ctx.session.state["extraction_input"]
        result = await (_extract_image(inp) if inp["modality"] == "image" else _extract_voice(inp))
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=json.dumps(result))]),
        )


# The single root instance. sub_agents declares the tree (structure); execution
# builds goal-injected copies of these same three and runs them per call.
note_extraction_orchestrator = NoteExtractionOrchestrator(
    name="note_extraction_orchestrator",
    description="Routes shift-note extraction to the voice or image sub-agents by input modality.",
    sub_agents=[narrative_extractor, observation_extractor, progress_note_extractor],
)


async def run_extraction(modality: str, **inputs) -> dict:
    """Drive the orchestrator once via a fresh runner; return its result dict.

    modality: 'voice' or 'image'. `inputs` (bytes/goals/toggles/pages) are placed
    in session state for the root to route on. Returns {"section1","section2"}
    for voice or {"note"} for image.
    """
    runner = InMemoryRunner(agent=note_extraction_orchestrator, app_name=APP_NAME)
    state = {"extraction_input": {"modality": modality, **inputs}}
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, state=state
    )
    trigger = types.Content(role="user", parts=[types.Part(text="extract")])
    text = None
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=trigger
    ):
        if event.content and event.content.parts and event.content.parts[0].text is not None:
            text = event.content.parts[0].text
    return json.loads(text)
