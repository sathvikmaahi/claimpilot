from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field
from typing import Literal

from agents.prompts import load_prompt
# Reuse the EXACT voice sub-models so the image note shape is provably identical
# to the narrative_extractor's — /submit cannot tell the two pipelines apart.
from agents.narrative_extractor.agent import ActivityTime, GoalAddressed, Confidence


class ProgressNoteExtraction(BaseModel):
    """The whole filled Progress Note, read from one photographed form.

    Sections 3-9 + 12 mirror the voice NarrativeExtraction field-for-field;
    Sections 10-11 (meals, personal_care) are extra because they are printed
    checkboxes on the paper form the DSP already filled in. The pre-printed
    Section 1-2 header is deliberately NOT here — it comes from the DB.
    """
    # --- Section 3-6: the core narrative (identical to NarrativeExtraction) ---
    transcript: str = Field(
        description="Faithful transcription of the Section 3 care-session narrative")
    activities_performed: list[str] = Field(
        description="Each distinct activity listed in Section 4, one per line")
    activity_timestamps: list[ActivityTime] = Field(
        description="Times only for activities with a time written next to them; usually empty")
    support_level: Literal["independent", "verbal", "physical", "full", "unknown"] = Field(
        description="The ONE checked box in Section 5; unknown if none is checked")
    individual_response: str = Field(
        description="Section 6 recipient engagement notes")

    # --- Section 7-9: observations (service folds these into extracted_fields_section2) ---
    health_observations: str | None = Field(
        default=None,
        description="Section 7 free text; null if 'None observed' is checked or it is blank")
    behavioral_observations: str | None = Field(
        default=None,
        description="Section 8 free text; null if 'None observed' is checked or it is blank")
    community_outing: str | None = Field(
        default=None,
        description="Section 9 description; null if 'No' is checked or it is blank")

    # --- Section 10-11: tap-style checkboxes the DSP already ticked on paper ---
    meals: list[str] = Field(
        default_factory=list,
        description="Checked Section 10 boxes, any of: Breakfast, Lunch, Dinner, Snack")
    personal_care: list[str] = Field(
        default_factory=list,
        description="Checked Section 11 boxes, any of: Bathing, Grooming, Toileting, Dressing")

    # --- Section 12: goals addressed (identical sub-model to voice) ---
    isp_goals_addressed: list[GoalAddressed] = Field(
        description="Active goals whose Section 12 box is checked; empty list if none")

    # --- Honest legibility-based confidence (identical sub-model to voice) ---
    confidence: Confidence = Field(
        description="Honest 0.0-1.0 confidence per field, reflecting legibility")


def build_progress_note_extractor(goals_text: str) -> Agent:
    """Build the Progress Note vision extractor with the recipient's active goals
    supplied at call time (from the DB), exactly like build_narrative_extractor."""
    return Agent(
        model="gemini-2.5-flash",
        name="progress_note_extractor",
        description="Extracts the structured Progress Note fields from a photographed paper form.",
        instruction=load_prompt("progress_note_extractor").replace("{goals_text}", goals_text),
        output_schema=ProgressNoteExtraction,
    )


# A ready default instance under a descriptive name. Production injects the
# recipient's goals per call via build_progress_note_extractor() above; this
# instance exists for ad-hoc local use, not as a package "root".
progress_note_extractor = build_progress_note_extractor("(no goals loaded)")
