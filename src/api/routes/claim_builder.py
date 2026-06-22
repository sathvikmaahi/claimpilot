"""
Stub — Step 3 Claim Builder route.

Input: service_event_id (UUID path param) — must have passed Step 2 validation.
Description: Triggers the Claim Builder agent to produce a 837P EDI file from the validated
             service event. Creates a draft claim row in the claims table, invokes the agent,
             and stores the generated EDI file reference. Returns the ClaimRead schema so the
             caller can proceed to Step 4 (Clerk Review).
             Uses Google ADK + Gemini 2.5 Pro for intelligent field mapping and EDI transformations.
Output: 200 ClaimRead with claim_status="draft" and 837P file reference | 404 | 500 on agent failure.
"""
from fastapi import APIRouter

router = APIRouter()
