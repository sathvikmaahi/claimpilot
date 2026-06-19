"""
Stub — Step 4 Clerk Review route.

Input: claim_id (UUID path param) + optional billing field overrides in request body.
Description: Serves the billing clerk review screen. Returns the draft claim split into:
             Service Fields (SF) — read-only: participant name/DCN, service date, shift times,
             service location, activities, DSP name/signature, EVV status.
             Billing Fields (BF) — editable: procedure code, modifiers, units, billed amount,
             rendering NPI, billing NPI, patient auth number, waiver type, diagnosis code, payer ID.
             On clerk POST /confirm, applies any BF corrections, sets claim_status="confirmed",
             records clerk_reviewed_by and clerk_review_timestamp, and returns the final ClaimRead.
             The confirmed 837P EDI file is the terminal output of Pipeline B.
Output: GET 200 ClaimRead (draft for review) | POST /confirm 200 ClaimRead (confirmed, final output).
"""
from fastapi import APIRouter

router = APIRouter()
