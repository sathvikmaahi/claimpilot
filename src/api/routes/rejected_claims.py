"""
Rejected Claims routes.

GET /rejected-claims/{claim_id}  — full detail for the Rejected Claim Detail screen.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from core.exceptions import ClaimBuildError
from schemas.claim import RejectedClaimRead, TriageResponse
from services.rejected_claims_service import get_rejected_claim
from services.triage_service import triage_claim

router = APIRouter()


@router.get(
    "/rejected-claims/{claim_id}",
    response_model=RejectedClaimRead,
    status_code=200,
    responses={
        404: {"description": "Claim not found or not a rejected claim."},
    },
)
async def get_rejected_claim_detail(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RejectedClaimRead:
    try:
        return await get_rejected_claim(claim_id=claim_id, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/rejected-claims/{claim_id}/triage",
    response_model=TriageResponse,
    status_code=200,
    responses={
        404: {"description": "Claim not found or not a rejected claim."},
        502: {"description": "Triage agent failed."},
    },
)
async def run_triage(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TriageResponse:
    try:
        return await triage_claim(claim_id=claim_id, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClaimBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
