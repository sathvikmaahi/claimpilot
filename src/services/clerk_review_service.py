"""
Stub — Step 4: Clerk Review.

Input: draft ClaimRead from Step 3 + optional billing field corrections from the clerk.
Description: Presents the billing clerk with a two-panel view:
             Service Fields (SF) — read-only fields from Pipeline A (participant, shift times, activities, DSP signature, EVV status).
             Billing Fields (BF) — editable fields built by the Claim Builder (procedure code, modifiers, units, billed amount,
             rendering NPI, billing NPI, patient auth number, waiver type, diagnosis code, payer ID).
             SF is read-only because it is the DSP's legal sign-off from Pipeline A — modifying it would
             constitute falsification of a legal document. BF represents administrative coding decisions
             the clerk owns and can correct before confirming.
             On clerk Confirm, updates claim_status to "confirmed" and records clerk_reviewed_by + clerk_review_timestamp.
Output: Confirmed ClaimRead with claim_status="confirmed". This is the final output of Pipeline B.
"""
import uuid
from schemas.claim import ClaimRead


async def confirm_claim(claim_id: uuid.UUID, clerk_id: str, billing_field_overrides: dict) -> ClaimRead:
    raise NotImplementedError("Step 4 clerk review not yet implemented.")
