"""
Stub — Step 3: Claim Builder (orchestration layer).

Input: Validated EnrichedServiceEvent from Step 2 + Life Unlimited billing config (NPI, Tax ID, payer ID, fee schedule).
Description: Orchestrates the Claim Builder agent (agents/claim_builder/agent.py) to produce a 837P EDI file.
             This service layer handles the lifecycle: creates a draft claims row, invokes the agent,
             updates the row with the generated 837P file reference, and returns a ClaimRead schema.
             The agent performs the actual field mapping and EDI transformations (name splitting,
             date formatting, diagnosis code qualification, procedure + modifier concatenation, etc.).
Output: ClaimRead schema with claim_status="draft" and the 837P file reference populated.
        Raises ClaimBuildError if the agent cannot produce a valid EDI file.
"""
from schemas.service_event import EnrichedServiceEvent
from schemas.claim import ClaimRead
from core.exceptions import ClaimBuildError


async def build_claim(event: EnrichedServiceEvent) -> ClaimRead:
    raise NotImplementedError("Step 3 claim builder not yet implemented.")
