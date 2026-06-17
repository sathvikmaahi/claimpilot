from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field
from typing import Literal


FIELD_GUIDANCE = {
    "health": "a HEALTH observation (symptoms, skin/rash, appetite, sleep, injury, pain)",
    "behavioral": "a BEHAVIORAL observation (mood, agitation, restlessness, engagement, an incident)",
    "outing": "details of a COMMUNITY OUTING (where they went, how long, what happened)",
}


class Section2(BaseModel):
    value: str = Field(description="A concise clinical note for the one target topic only")
    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Honest confidence in the extracted value")


def build_section2_agent(field: str) -> Agent:
    """Build a Section 2 agent locked to ONE field. The orchestrator calls this per toggle."""
    if field not in FIELD_GUIDANCE:
        raise ValueError(f"Unknown field {field!r}; expected one of {list(FIELD_GUIDANCE)}")
    return Agent(
        model="gemini-2.5-flash",
        name=f"section2_{field}_agent",
        description="Extracts a single observation field from a short DSP narration.",
        instruction=(
            "You extract ONE specific field from a Direct Support Professional's short "
            "spoken note. The user's message IS the note.\n"
            f"Extract ONLY this: {FIELD_GUIDANCE[field]}.\n"
            "Do NOT include anything about any other topic, even if the DSP mentions it. "
            "If the note doesn't actually contain this topic, set value to an empty string "
            "and confidence to 'Low'. Never invent details."
        ),
        output_schema=Section2,
    )


# Default instance so the folder stays discoverable (`adk run section2_agent`).
root_agent = build_section2_agent("health")