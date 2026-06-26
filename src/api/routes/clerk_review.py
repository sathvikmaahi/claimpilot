"""
Step 4 Clerk Review route.

Input: claim_id (UUID path param) + optional billing field overrides in request body.
Description: Serves the billing clerk review screen. Returns the draft claim split into:
             Service Fields (SF) — read-only: participant name/DCN, service date, shift times,
             service location, activities, DSP name/signature, EVV status.
             Billing Fields (BF) — editable: procedure code, modifiers, units, billed amount,
             rendering NPI, billing NPI, waiver type, diagnosis code, payer ID.
             On clerk POST /confirm, applies any BF corrections, sets claim_status="confirmed",
             records clerk_reviewed_by and clerk_review_timestamp, and returns the final ClaimRead.
             The confirmed 837P EDI file is the terminal output of Pipeline B.
Output: GET 200 ClaimRead (draft for review) | POST /confirm 200 ClaimRead (confirmed, final output).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from schemas.claim import ClerkReviewRead, ClerkReviewConfirmRequest, ClaimRead
from services.clerk_review_service import confirm_claim, get_clerk_review_data

router = APIRouter()


@router.get(
    "/clerk-review/{claim_id}",
    response_model=ClerkReviewRead,
    status_code=200,
    responses={
        404: {"description": "Claim or claim fields not found for the given claim_id."},
    },
)
async def get_clerk_review(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ClerkReviewRead:
    try:
        return await get_clerk_review_data(claim_id=claim_id, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/clerk-review/{claim_id}/confirm",
    response_model=ClaimRead,
    status_code=200,
    responses={
        404: {"description": "Claim not found for the given claim_id."},
    },
)
async def confirm_clerk_review(
    claim_id: uuid.UUID,
    request: ClerkReviewConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> ClaimRead:
    try:
        return await confirm_claim(
            claim_id=claim_id,
            clerk_id=request.clerk_id,
            billing_field_overrides=request.billing_field_overrides,
            db=db,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
