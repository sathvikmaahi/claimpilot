"""
Stub — Claim Builder Agent (Google ADK + Gemini 2.5 Pro).

Input: Validated EnrichedServiceEvent + Life Unlimited billing config dict.
Description: The only AI agent in Pipeline B. Used for Step 3 because building a valid 837P EDI file
             requires intelligent transformations beyond simple field mapping:
             — Name splitting: "John Smith" → NM1 segment "SMITH*JOHN"
             — Date formatting: "2026-06-11" → DTP segment "D8*20260611"
             — Diagnosis code qualification: "F70" → HI segment "ABK:F70"
             — Procedure + modifier concatenation: T2016 + UP → SV1 "HC:T2016:UP"
             — Location → place of service code: ISL home → CLM05 code 12 (Home)
             — Billed amount lookup: T2016 → fee schedule rate → SV102
             — Claim ID generation: unique CLM01 control number per claim
             — Segment count: SE01 total segment count for the EDI transaction
             Built on Google ADK (Python) with Gemini 2.5 Pro. Observability via ADK Web UI + Cloud Trace.
Output: Raw 837P EDI string — valid ISA/GS envelope with all required segments populated.
        Raises ClaimBuildError if any required field is missing or transformation fails.
"""
from schemas.service_event import EnrichedServiceEvent
from core.exceptions import ClaimBuildError


async def run_claim_builder_agent(event: EnrichedServiceEvent, billing_config: dict) -> str:
    raise NotImplementedError("Claim Builder agent not yet implemented — requires Google ADK setup.")
