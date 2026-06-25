"""
Step 3 Claim Builder route.

Input: service_event_id (UUID path param) — must have passed Step 2 validation.
Description: Fetches the validated service event, runs the Claim Builder agent to
             produce structured 837P fields, writes a draft claim row to the DB,
             and returns ClaimRead for Step 4 (Clerk Review).
             On agent failure after retries: marks claim as draft_failed and raises 500.
             Uses Google ADK + Gemini 2.5 Flash for intelligent field mapping.
Output: 200 ClaimRead (claim_status="draft") | 404 | 502 auth API down | 503 DB down | 500 agent failure.
"""
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agents.claim_builder.agent import ClaimFields, run_claim_builder
from agents.claim_builder.edi_generator import generate_837p
from api.dependencies import get_db, get_http_client, get_settings
from core.config import Settings
from core.exceptions import (
    AuthAPIUnavailableError,
    ClaimBuildError,
    DatabaseUnavailableError,
    ServiceEventNotFoundError,
)
from db.models.claims import Claim
from schemas.claim import ClaimRead
from services.fetch_service import fetch_service_event

router = APIRouter()


def _make_claim_read(claim: Claim) -> ClaimRead:
    return ClaimRead(
        claim_id=claim.claim_id,
        service_event_id=claim.service_event_id,
        patient_auth_number=claim.patient_auth_number,
        billing_npi=claim.billing_npi or "",
        payer_id=claim.payer_id or "",
        billed_amount=claim.billed_amount or 0,
        claim_status=claim.claim_status,
        file_837p_reference=claim.file_837p_reference,
        clerk_reviewed_by=claim.clerk_reviewed_by,
        clerk_review_timestamp=claim.clerk_review_timestamp,
        created_at=claim.created_at,
    )


@router.get(
    "/claim-builder/{service_event_id}",
    response_model=ClaimRead,
    status_code=200,
    responses={
        404: {"description": "No documented_care_sessions record found for this service_event_id."},
        500: {"description": "Claim Builder agent failed to produce a valid 837P field set."},
        502: {"description": "Mock Medicaid authorization API is unreachable or timed out."},
        503: {"description": "Cloud SQL query failed — database unavailable."},
    },
)
async def build_claim(
    service_event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> ClaimRead:
    """
    Input: service_event_id (UUID path parameter) — must have passed Step 2 validation.
    Description: Step 3 — fetches the enriched service event, runs the Claim Builder
                 agent to map fields to 837P EDI structure, writes draft claim to DB.
                 PASS → returns ClaimRead with claim_status="draft" for Step 4 review.
                 FAIL → marks claim as draft_failed and returns 500.
    Output: 200 ClaimRead ready for Step 4 (Clerk Review).
    """
    # 1 — Fetch the validated service event
    try:
        event = await fetch_service_event(
            service_event_id=service_event_id,
            db=db,
            http_client=http_client,
            auth_api_url=settings.mock_auth_api_url,
            auth_api_timeout=settings.auth_api_timeout,
        )
    except ServiceEventNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthAPIUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # 2 — Run the Claim Builder agent
    claim = Claim(
        service_event_id=event.service_event_id,
        patient_auth_number=event.authorization.patient_prior_auth_number,
        billing_npi=settings.billing_npi,
        payer_id=settings.payer_id,
        claim_status="draft",
    )
    db.add(claim)
    await db.flush()  # get claim_id without committing

    try:
        fields: ClaimFields = await run_claim_builder(
            event=event,
            fee_rate=settings.t2016_fee_schedule_rate,
        )
    except ClaimBuildError as exc:
        claim.claim_status = "draft_failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 3 — Generate 837P EDI and update claim
    from decimal import Decimal
    edi_text = generate_837p(
        fields=fields,
        billing_npi=settings.billing_npi,
        tax_id=settings.tax_id,
        payer_id=settings.payer_id,
        claim_id=claim.claim_id,
    )
    claim.billed_amount = Decimal(fields.billed_amount)
    claim.file_837p_reference = edi_text   # stored as text for POC; production would write to GCS
    claim.claim_status = "draft"
    await db.commit()

    return _make_claim_read(claim)
