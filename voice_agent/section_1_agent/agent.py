from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field
from typing import Literal


class ActivityTime(BaseModel):
    activity: str = Field(description="The activity")
    time: str = Field(description="When it happened, e.g. '8:00am', or '~10:00am' if approximate")


class GoalAddressed(BaseModel):
    goal_id: str = Field(description="The goal_id of the matched active goal")
    category: Literal["daily_living", "community", "health_safety", "employment", "social"]
    evidence: str = Field(description="The phrase from the narration that justifies this mapping")


class Confidence(BaseModel):
    activities_performed: Literal["High", "Medium", "Low"]
    activity_timestamps: Literal["High", "Medium", "Low"]
    support_level: Literal["High", "Medium", "Low"]
    individual_response: Literal["High", "Medium", "Low"]


class Section1(BaseModel):
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
        description="Honest High/Medium/Low confidence for each field")


def build_section1_agent(goals_text: str) -> Agent:
    """Build the Section 1 agent with goals supplied at call time (from the DB)."""
    return Agent(
        model="gemini-2.5-flash",
        name="section1_agent",
        description="Extracts structured Section 1 activity data from a DSP shift narration.",
        instruction=(
            "You extract structured documentation from a Direct Support Professional's "
            "shift narration (spoken audio or text). The user's message IS the narration. "
            "Extract only what is actually said — never invent details. "
            "If a time is approximate ('around ten'), prefix it with '~'. "
            "If the support level isn't inferable, use 'unknown'.\n\n"
            "Map activities to the individual's ACTIVE ISP GOALS below, but ONLY when the "
            "narration gives clear evidence. Do not map vague mentions. If nothing clearly "
            "maps, return an empty list.\n"
            "ACTIVE ISP GOALS:\n" + goals_text
        ),
        output_schema=Section1,
    )


# Default instance keeps the folder discoverable for `adk run section1_agent`.
root_agent = build_section1_agent("(no goals loaded)")