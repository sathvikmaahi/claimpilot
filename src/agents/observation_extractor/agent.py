from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field
from typing import Literal

from agents.prompts import load_prompt


FIELD_GUIDANCE = {
    "health": "a HEALTH observation (symptoms, skin/rash, appetite, sleep, injury, pain)",
    "behavioral": "a BEHAVIORAL observation (mood, agitation, restlessness, engagement, an incident)",
    "outing": "details of a COMMUNITY OUTING (where they went, how long, what happened)",
}


class Observation(BaseModel):
    value: str = Field(description="A concise clinical note for the one target topic only")
    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Honest confidence in the extracted value")


def build_observation_extractor(field: str) -> Agent:
    """Build an observation extractor locked to ONE field. The orchestrator calls this per toggle."""
    if field not in FIELD_GUIDANCE:
        raise ValueError(f"Unknown field {field!r}; expected one of {list(FIELD_GUIDANCE)}")
    return Agent(
        model="gemini-2.5-flash",
        name=f"observation_extractor_{field}",
        description="Extracts a single observation field from a short DSP narration.",
        instruction=load_prompt("observation_extractor").format(field_guidance=FIELD_GUIDANCE[field]),
        output_schema=Observation,
    )


# Default instance so the folder stays discoverable (`adk run observation_extractor`).
root_agent = build_observation_extractor("health")