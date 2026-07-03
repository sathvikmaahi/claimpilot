"""
Rejected Claims routes.

GET  /rejected-claims/{claim_id}          — full detail for the Rejected Claim Detail screen.
POST /rejected-claims/{claim_id}/run-pipeline — orchestrator: triage → correction | appeal | write-off.
POST /rejected-claims/{claim_id}/resubmit     — clerk approves correction and creates new claim.
POST /rejected-claims/{claim_id}/submit-appeal — clerk approves appeal draft and stores it.
POST /rejected-claims/{claim_id}/write-off    — clerk writes off the claim (no agent needed).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from core.exceptions import ClaimBuildError
from schemas.claim import (
    PipelineOutput,
    RejectedClaimRead,
    ResubmitRequest,
    ResubmitResponse,
)
from services.correction_service import resubmit_claim
from services.rejection_pipeline_service import run_pipeline_for_claim
from services.rejected_claims_service import get_rejected_claim

router = APIRouter()


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get(
    "/rejected-claims/{claim_id}",
    response_model=RejectedClaimRead,
    status_code=200,
    responses={404: {"description": "Claim not found or not a rejected claim."}},
)
async def get_rejected_claim_detail(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RejectedClaimRead:
    try:
        return await get_rejected_claim(claim_id=claim_id, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Orchestrator pipeline ─────────────────────────────────────────────────────

@router.post(
    "/rejected-claims/{claim_id}/run-pipeline",
    response_model=PipelineOutput,
    status_code=200,
    responses={
        404: {"description": "Claim not found or not a rejected claim."},
        502: {"description": "Orchestrator or sub-agent failed."},
    },
)
async def run_pipeline(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineOutput:
    try:
        return await run_pipeline_for_claim(claim_id=claim_id, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClaimBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Clerk actions (human-in-the-loop) ────────────────────────────────────────

@router.post(
    "/rejected-claims/{claim_id}/resubmit",
    response_model=ResubmitResponse,
    status_code=201,
    responses={
        404: {"description": "Claim not found or not correctable."},
        502: {"description": "EDI structural validation failed."},
    },
)
async def run_resubmit(
    claim_id: uuid.UUID,
    body: ResubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> ResubmitResponse:
    try:
        return await resubmit_claim(claim_id=claim_id, request=body, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClaimBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class AppealSubmitRequest(BaseModel):
    clerk_id: str
    appeal_text: str  # clerk may edit the draft before submitting


@router.post(
    "/rejected-claims/{claim_id}/submit-appeal",
    status_code=200,
)
async def submit_appeal(
    claim_id: uuid.UUID,
    body: AppealSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select
    from db.models.claims import Claim, ClaimRejection
    from datetime import datetime, timezone

    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    if claim.claim_status != "rejected":
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} is not a rejected claim")

    rejection = (
        await db.execute(select(ClaimRejection).where(ClaimRejection.claim_id == claim_id))
    ).scalar_one_or_none()
    if rejection is None:
        raise HTTPException(status_code=404, detail=f"No rejection record for claim {claim_id}")

    claim.claim_status = "appeal_submitted"
    rejection.appeal_packet_text = body.appeal_text
    rejection.resolution_action = "appeal"
    rejection.resolution_status = "in_progress"
    rejection.resolved_by = body.clerk_id
    rejection.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "appeal_submitted", "claim_id": str(claim_id)}


class WriteOffRequest(BaseModel):
    clerk_id: str
    reason: str


@router.post(
    "/rejected-claims/{claim_id}/write-off",
    status_code=200,
)
async def write_off(
    claim_id: uuid.UUID,
    body: WriteOffRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import select
    from db.models.claims import Claim, ClaimRejection
    from datetime import datetime, timezone

    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    if claim.claim_status != "rejected":
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} is not a rejected claim")

    rejection = (
        await db.execute(select(ClaimRejection).where(ClaimRejection.claim_id == claim_id))
    ).scalar_one_or_none()
    if rejection is None:
        raise HTTPException(status_code=404, detail=f"No rejection record for claim {claim_id}")

    claim.claim_status = "written_off"
    rejection.resolution_action = "write_off"
    rejection.resolution_status = "resolved"
    rejection.resolved_by = body.clerk_id
    rejection.resolved_at = datetime.now(timezone.utc)
    if rejection.triage_agent_output is None:
        rejection.triage_agent_output = {}
    rejection.triage_agent_output["write_off_reason"] = body.reason
    await db.commit()

    return {"status": "written_off", "claim_id": str(claim_id)}
