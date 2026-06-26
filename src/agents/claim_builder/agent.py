"""
Step 3: Claim Builder agent.

Receives a validated EnrichedServiceEvent + billing rules and produces a
structured ClaimFields object containing every 837P field needed to generate
the EDI file. The LLM handles field mapping and name parsing; billing codes
and constants come from billing_rules.py — the agent never invents them.
"""
import asyncio
import json
from decimal import Decimal

from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field

from agents.claim_builder import billing_rules
from agents.prompts import load_prompt
from core.exceptions import ClaimBuildError
from schemas.service_event import EnrichedServiceEvent

APP_NAME = "claimpilot_claim_builder"
USER_ID = "pipeline_b"


# ---------------------------------------------------------------------------
# Output schema — the agent populates every field from service_event + billing_rules
# ---------------------------------------------------------------------------

class ClaimFields(BaseModel):
    """Structured 837P field set produced by the Claim Builder agent."""

    # Loop 2000B — Subscriber
    subscriber_last_name: str = Field(description="Parsed from participant_name")
    subscriber_first_name: str | None = Field(description="Parsed from participant_name; null if single name")
    subscriber_medicaid_id: str = Field(description="participant_dcn — MO 9-digit Medicaid ID")
    subscriber_dob: str = Field(description="participant_dob formatted YYYYMMDD")
    subscriber_sex: str = Field(description="M, F, or U from care_recipients.sex")

    # Loop 2300 — Claim
    service_date: str = Field(description="service_date formatted YYYYMMDD")
    service_begin_time: str | None = Field(description="begin_time as HHMM; null if not recorded")
    service_end_time: str | None = Field(description="end_time as HHMM; null if not recorded")
    diagnosis_code: str = Field(description="ICD-10 diagnosis code")
    diagnosis_qualifier: str = Field(description="From billing_rules — always ABK")
    place_of_service: str = Field(description="From billing_rules — CMS place of service code")
    claim_filing_indicator: str = Field(description="From billing_rules — MC for Medicaid")

    # Loop 2310B — Rendering Provider
    rendering_npi: str = Field(description="rendering_npi from staff_shift_assignments")

    # Loop 2400 — Service Line
    procedure_code: str = Field(description="procedure_code from service_event")
    procedure_qualifier: str = Field(description="From billing_rules — always HC")
    modifier_1: str = Field(description="modifier_1 — required by MO HealthNet for T2016")
    modifier_2: str | None = Field(description="modifier_2 or null")
    modifier_3: str | None = Field(description="modifier_3 or null")
    service_units: int = Field(description="billable_units_calculated")
    billed_amount: str = Field(description="service_units × fee schedule rate as '0.00' string")

    # Taxonomy
    taxonomy_code: str = Field(description="From billing_rules — billing provider taxonomy")

    # Optional notes from agent
    notes: str | None = Field(default=None, description="Agent notes on any mapping decisions")


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

def build_claim_builder() -> Agent:
    return Agent(
        model="gemini-2.5-flash",
        name="claim_builder",
        description="Maps a validated EnrichedServiceEvent to structured 837P EDI fields.",
        instruction=load_prompt("claim_builder"),
        output_schema=ClaimFields,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _build_user_message(event: EnrichedServiceEvent, fee_rate: Decimal) -> str:
    """Serialise the event + billing rules into the agent's user message."""
    rules_payload = {
        "PROCEDURE_CODE": billing_rules.PROCEDURE_CODE,
        "PROCEDURE_CODE_QUALIFIER": billing_rules.PROCEDURE_CODE_QUALIFIER,
        "CLAIM_FILING_INDICATOR": billing_rules.CLAIM_FILING_INDICATOR,
        "PLACE_OF_SERVICE_CODE": billing_rules.PLACE_OF_SERVICE_CODE,
        "BILLING_PROVIDER_TAXONOMY": billing_rules.BILLING_PROVIDER_TAXONOMY,
        "DIAGNOSIS_CODE_QUALIFIER": billing_rules.DIAGNOSIS_CODE_QUALIFIER,
        "fee_schedule_rate": str(fee_rate),
        "VALID_MODIFIERS": billing_rules.VALID_MODIFIERS,
        "FIELD_MAP": billing_rules.FIELD_MAP,
    }
    return json.dumps({
        "service_event": event.model_dump(mode="json"),
        "billing_rules": rules_payload,
    }, indent=2)


async def run_claim_builder(
    event: EnrichedServiceEvent,
    fee_rate: Decimal,
) -> ClaimFields:
    """
    Run the Claim Builder agent and return structured ClaimFields.

    Retry strategy:
      - Transient API failure (429 / timeout) → auto-retry up to 2× with backoff
      - ClaimBuildError raised on persistent failure → route marks claim draft_failed
    """
    agent = build_claim_builder()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    user_message = _build_user_message(event, fee_rate)

    async def _run() -> ClaimFields:
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
            raise ClaimBuildError("Agent returned no response.")
        return ClaimFields.model_validate_json(text)

    return await _with_retry(_run)


async def _with_retry(coro_factory, *, attempts: int = 3, base_delay: float = 2.0):
    """Retry on transient quota/rate-limit errors with exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except ClaimBuildError:
            raise  # not retryable — surface immediately
        except Exception as exc:
            is_quota = "429" in str(exc) or "quota" in str(exc).lower() or "rate" in str(exc).lower()
            if not is_quota or attempt == attempts:
                raise ClaimBuildError(f"Claim builder failed after {attempt} attempt(s): {exc}") from exc
            delay = base_delay * (2 ** (attempt - 1))
            await asyncio.sleep(delay)


# ADK discoverability
root_agent = build_claim_builder()
