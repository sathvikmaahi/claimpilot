"""
Triage Agent — classifies a rejected claim into correctable / appeal / write_off.

Context (claim fields, rejection detail, prior history) is pre-fetched by the
service layer and injected into the prompt. The agent reasons over the CARC/RARC
codes and claim data, then returns a structured TriageOutput.
"""
import asyncio
import json

from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from agents.prompts import load_prompt
from core.exceptions import ClaimBuildError

APP_NAME = "claimpilot_triage"
USER_ID = "pipeline_b"


class TriageOutput(BaseModel):
    triage_category: str   # "correctable" | "appeal" | "write_off"
    confidence: str        # "high" | "medium" | "low"
    reasoning: str
    recommended_action: str


def build_triage_agent() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="triage_agent",
        description="Classifies a rejected Medicaid claim into correctable, appeal, or write_off.",
        instruction=load_prompt("triage"),
        output_schema=TriageOutput,
    )


def _build_triage_message(rejection: dict, claim_fields: dict, claim_history: list[dict]) -> str:
    return json.dumps({
        "rejection": rejection,
        "claim_fields": claim_fields,
        "claim_history": claim_history,
    }, indent=2, default=str)


async def run_triage(
    rejection: dict,
    claim_fields: dict,
    claim_history: list[dict],
) -> TriageOutput:
    agent = build_triage_agent()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    user_message = _build_triage_message(rejection, claim_fields, claim_history)

    async def _run() -> TriageOutput:
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
            raise ClaimBuildError("Triage agent returned no response.")
        return TriageOutput.model_validate_json(text)

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
                raise ClaimBuildError(f"Triage agent failed after {attempt} attempt(s): {exc}") from exc
            delay = base_delay * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
