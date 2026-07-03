"""
Correction Agent — proposes field corrections for a correctable rejected claim.

Context (claim fields, rejection detail, billing rules) is pre-fetched by the
service layer and injected into the prompt. The agent returns a structured
CorrectionOutput with only the fields that need to change.
"""
import asyncio
import json

from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from agents.prompts import load_prompt
from core.exceptions import ClaimBuildError

APP_NAME = "claimpilot_correction"
USER_ID = "pipeline_b"


class CorrectionOutput(BaseModel):
    proposed_fields: dict[str, str]   # field_name -> corrected value (only changed fields)
    reasoning: str
    confidence: str                   # "high" | "medium" | "low"


def build_correction_agent() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="correction_agent",
        description="Proposes minimum field corrections for a correctable rejected Medicaid claim.",
        instruction=load_prompt("correction"),
        output_schema=CorrectionOutput,
    )


def _build_correction_message(
    rejection: dict,
    claim_fields: dict,
    billing_rules: dict,
) -> str:
    return json.dumps(
        {
            "rejection": rejection,
            "claim_fields": claim_fields,
            "billing_rules": billing_rules,
        },
        indent=2,
        default=str,
    )


async def run_correction(
    rejection: dict,
    claim_fields: dict,
    billing_rules: dict,
) -> CorrectionOutput:
    agent = build_correction_agent()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    user_message = _build_correction_message(rejection, claim_fields, billing_rules)

    async def _run() -> CorrectionOutput:
        text = None
        message = types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )
        async for evt in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            if evt.is_final_response() and evt.content:
                text = evt.content.parts[0].text
        if text is None:
            raise ClaimBuildError("Correction agent returned no response.")
        return CorrectionOutput.model_validate_json(text)

    return await _with_retry(_run)


async def _with_retry(coro_factory, *, attempts: int = 3, base_delay: float = 2.0):
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except ClaimBuildError:
            raise
        except Exception as exc:
            is_quota = "429" in str(exc) or "quota" in str(exc).lower() or "rate" in str(exc).lower()
            if not is_quota or attempt == attempts:
                raise ClaimBuildError(f"Correction agent failed after {attempt} attempt(s): {exc}") from exc
            delay = base_delay * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
