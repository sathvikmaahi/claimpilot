from google.adk.agents.llm_agent import Agent
from google.genai import types
from pydantic import BaseModel, Field

from agents.prompts import load_prompt


FIELD_GUIDANCE = {
    "health": "a HEALTH observation (symptoms, skin/rash, appetite, sleep, injury, pain)",
    "behavioral": "a BEHAVIORAL observation (mood, agitation, restlessness, engagement, an incident)",
    "outing": "details of a COMMUNITY OUTING (where they went, how long, what happened)",
}


class Observation(BaseModel):
    value: str = Field(description="A concise clinical note for the one target topic only")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Honest confidence from 0.0 (none) to 1.0 (certain)")


def build_observation_extractor(field: str) -> Agent:
    """Build an observation extractor locked to ONE field. The orchestrator calls this per toggle."""
    if field not in FIELD_GUIDANCE:
        raise ValueError(f"Unknown field {field!r}; expected one of {list(FIELD_GUIDANCE)}")
    return Agent(
        model="gemini-2.5-flash",
        name=f"observation_extractor_{field}",
        description="Extracts a single observation field from a short DSP narration.",
        instruction=load_prompt("observation_extractor").replace("{field_guidance}", FIELD_GUIDANCE[field]),
        output_schema=Observation,
        generate_content_config=types.GenerateContentConfig(
            # Single-field extraction needs little reasoning; a small thinking budget
            # keeps each call fast and cheap (called once per toggled observation).
            thinking_config=types.ThinkingConfig(thinking_budget=512),
        ),
    )


# Default instance so the folder stays discoverable (`adk run observation_extractor`).
root_agent = build_observation_extractor("health")