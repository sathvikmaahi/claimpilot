from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field

from agents.prompts import load_prompt


class Transcription(BaseModel):
    transcript: str = Field(
        description="Faithful transcription of the spoken note, with light filler removed")


def build_transcription_agent() -> Agent:
    """Build the transcription agent: faithfully turns a short spoken note into text.

    Stateless and write-free — used by /transcribe for voice notes (e.g. per-goal
    notes): audio in, text out. It is told NOT to interpret, structure, or
    embellish, only to write down what was said while lightly cleaning filler;
    faithfulness matters because this can support Medicaid billing.
    """
    return Agent(
        model="gemini-2.5-flash",
        name="transcription_agent",
        description="Faithfully transcribes a short spoken note to text.",
        instruction=load_prompt("transcription_agent"),
        output_schema=Transcription,
    )


# A ready default instance under a descriptive name, built once and reused (the
# agent is identical for every note). Production calls it via this instance.
transcription_agent = build_transcription_agent()
