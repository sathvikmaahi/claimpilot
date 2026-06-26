from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field
from typing import Literal

from agents.prompts import load_prompt


class ActivityTime(BaseModel):
    activity: str = Field(description="The activity")
    time: str = Field(description="When it happened, e.g. '8:00am', or '~10:00am' if approximate")


class GoalAddressed(BaseModel):
    goal_id: str = Field(description="The goal_id of the matched active goal")
    category: Literal["daily_living", "community", "health_safety", "employment", "social"]
    evidence: str = Field(description="The phrase from the narration that justifies this mapping")


class Confidence(BaseModel):
    activities_performed: float = Field(ge=0.0, le=1.0, description="Confidence from 0.0 (none) to 1.0 (certain)")
    activity_timestamps: float = Field(ge=0.0, le=1.0, description="Confidence from 0.0 (none) to 1.0 (certain)")
    support_level: float = Field(ge=0.0, le=1.0, description="Confidence from 0.0 (none) to 1.0 (certain)")
    individual_response: float = Field(ge=0.0, le=1.0, description="Confidence from 0.0 (none) to 1.0 (certain)")


class NarrativeExtraction(BaseModel):
    transcript: str = Field(description="Faithful transcription of the narration")
    activities_performed: list[str] = Field(
        description="Each distinct activity the DSP did with the individual")
    activity_timestamps: list[ActivityTime] = Field(
        description="Times only for activities that have a stated or clearly implied time")
    support_level: Literal["independent", "verbal", "physical", "full", "unknown"] = Field(
        description="Overall support: verbal=prompts/reminders, physical=hands-on, "
                    "full=full assistance, independent=did it alone, unknown=not inferable")
    individual_response: str = Field(
        description="How the individual engaged, progressed, or felt")
    isp_goals_addressed: list[GoalAddressed] = Field(
        description="Active goals clearly addressed by the activities; empty list if none clearly apply")
    confidence: Confidence = Field(
        description="Honest 0.0-1.0 confidence for each field")


def build_narrative_extractor(goals_text: str) -> Agent:
    """Build the narrative extractor with goals supplied at call time (from the DB)."""
    return Agent(
        model="gemini-2.5-flash",
        name="narrative_extractor",
        description="Extracts structured activity-narrative data from a DSP shift narration.",
        instruction=load_prompt("narrative_extractor").replace("{goals_text}", goals_text),
        output_schema=NarrativeExtraction,
    )


# A ready default instance under a descriptive name. Production injects the
# recipient's goals per call via build_narrative_extractor() above; this
# instance exists for ad-hoc local use, not as a package "root".
narrative_extractor = build_narrative_extractor("(no goals loaded)")