"""
Rejection Pipeline Orchestrator — ADK multi-agent orchestration.

Wraps TriageAgent, CorrectionAgent, and AppealAgent as AgentTool instances.
The orchestrator LLM:
  1. Always calls triage_agent first
  2. Branches: correctable → correction_agent | appeal → appeal_agent | write_off → done
  3. Returns a single PipelineOutput JSON combining all sub-agent results

No output_schema on the orchestrator — it outputs raw JSON text that the service
layer parses into PipelineOutput. This avoids the Gemini function-calling /
response-schema conflict.
"""
import asyncio
import json
import re

from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools.agent_tool import AgentTool
from google.genai import types
from pydantic import BaseModel

from agents.appeal.agent import build_appeal_agent
from agents.correction.agent import build_correction_agent
from agents.prompts import load_prompt
from agents.triage.agent import build_triage_agent
from core.exceptions import ClaimBuildError

APP_NAME = "claimpilot_rejection_orchestrator"
USER_ID = "pipeline_b"


class PipelineOutput(BaseModel):
    triage_category: str
    triage_confidence: str
    triage_reasoning: str
    triage_recommended_action: str
    proposed_fields: dict[str, str] | None = None
    correction_reasoning: str | None = None
    correction_confidence: str | None = None
    appeal_draft: str | None = None
    appeal_confidence: str | None = None
    appeal_key_evidence: list[str] | None = None


def build_orchestrator() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="rejection_orchestrator",
        description="Orchestrates triage, correction, and appeal agents for a rejected Medicaid claim.",
        instruction=load_prompt("rejection_orchestrator"),
        tools=[
            AgentTool(agent=build_triage_agent()),
            AgentTool(agent=build_correction_agent()),
            AgentTool(agent=build_appeal_agent()),
        ],
        # No output_schema — orchestrator outputs text JSON parsed by the service layer.
        # Mixing output_schema with tools causes Gemini function-calling/response-schema conflicts.
    )


def _extract_json(text: str) -> str:
    """Pull the first complete JSON object out of the orchestrator's final text."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    # Find balanced braces
    start = text.find("{")
    if start == -1:
        raise ClaimBuildError("Orchestrator response contained no JSON object.")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ClaimBuildError("Orchestrator response contained malformed JSON.")


async def run_pipeline(context: dict) -> PipelineOutput:
    """
    Run the full rejection pipeline for one claim.

    `context` must contain keys: rejection, claim_fields, billing_rules,
    claim_history, progress_note.
    """
    agent = build_orchestrator()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )

    user_message = json.dumps(context, indent=2, default=str)

    async def _run() -> PipelineOutput:
        final_text: str | None = None
        message = types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )
        async for evt in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            if evt.is_final_response() and evt.content:
                for part in evt.content.parts:
                    if part.text:
                        final_text = part.text
                        break

        if final_text is None:
            raise ClaimBuildError("Orchestrator returned no final response.")

        raw_json = _extract_json(final_text)
        return PipelineOutput.model_validate_json(raw_json)

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
                raise ClaimBuildError(
                    f"Orchestrator failed after {attempt} attempt(s): {exc}"
                ) from exc
            delay = base_delay * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
