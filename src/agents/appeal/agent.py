"""
Appeal Agent — drafts a formal Medicaid appeal letter for appeal-category rejections.

Context (rejection detail, claim fields, DSP progress note) is injected as JSON.
Returns AppealOutput with the drafted letter, confidence, and key evidence cited.
"""
import json
from typing import Any

from google.adk.agents.llm_agent import Agent
from google.genai import types
from pydantic import BaseModel

from agents.prompts import load_prompt

APP_NAME = "claimpilot_appeal"
USER_ID = "pipeline_b"


class AppealOutput(BaseModel):
    appeal_draft: str
    confidence: str          # "high" | "medium" | "low"
    key_evidence: list[str]  # bullet points of evidence cited


def build_appeal_agent() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="appeal_agent",
        description=(
            "Drafts a formal Medicaid appeal letter for a rejected claim "
            "using DSP progress note documentation as clinical evidence."
        ),
        instruction=load_prompt("appeal"),
        output_schema=AppealOutput,
    )
