"""
Step 2 Validate route.

Input: service_event_id (UUID path param).
Description: Fetches the enriched service event (Step 1) then runs the 5 Pipeline B
             validation checks (Step 2) in sequence.
             Check 1a — Auth not expired (CO-197)
             Check 1b — Units not exhausted (CO-151)
             Check 2  — Service code matches authorization
             Check 3  — Individual enrolled in Comprehensive Waiver
             Check 4  — EVV GPS coordinates present
             Check 5  — All required 837P fields present
             PASS → 200 with validated EnrichedServiceEvent.
             FAIL → claim written to review queue (claims table, status=failed) + 422 returned.
Output: 200 EnrichedServiceEvent (PASS) | 422 with failure detail (FAIL) | 404 not found | 502 auth API down.
"""
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_http_client, get_settings
from core.config import Settings
from core.exceptions import AuthAPIUnavailableError, DatabaseUnavailableError, ServiceEventNotFoundError, ValidationFailedError
from db.models.claims import Claim
from schemas.service_event import EnrichedServiceEvent
from services.fetch_service import fetch_service_event
from services.validation_service import validate_service_event

router = APIRouter()


@router.get(
    "/validate/{service_event_id}",
    response_model=EnrichedServiceEvent,
    status_code=200,
    responses={
        404: {"description": "No matching record in Pipeline A tables for this service_event_id."},
        422: {"description": "Service event failed one of the 5 validation checks — written to review queue."},
        502: {"description": "Mock Medicaid authorization API is unreachable or timed out."},
        503: {"description": "Cloud SQL query failed — database unavailable."},
    },
)
async def validate_event(
    service_event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> EnrichedServiceEvent:
    """
    Input: service_event_id (UUID path parameter).
    Description: Step 2 — fetches the enriched service event then validates it against
                 5 Medicaid billing checks.
                 PASS → returns validated event for Step 3 (Claim Builder).
                 FAIL → writes claim to review queue (claim_status=failed) and returns 422.
                        Background revalidation job will re-check failed claims periodically.
    Output: 200 EnrichedServiceEvent ready for Step 3 (Claim Builder).
            422 with check number and reason if validation fails.
            404 if service_event_id not found in Pipeline A tables.
            502 if the mock auth API cannot be reached.
    """
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

    try:
        return await validate_service_event(event)
    except ValidationFailedError as exc:
        failed_claim = Claim(
            service_event_id=event.service_event_id,
            patient_auth_number=event.authorization.patient_prior_auth_number,
            claim_status="failed",
            validation_failure_check=exc.failures[0].check,
            validation_failure_reason=" | ".join(f.reason for f in exc.failures),
        )
        db.add(failed_claim)
        await db.commit()

        raise HTTPException(
            status_code=422,
            detail={
                "failures": [
                    {"check": f.check, "reason": f.reason}
                    for f in exc.failures
                ]
            },
        ) from exc
