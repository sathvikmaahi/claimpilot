import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_http_client, get_settings
from core.config import Settings
from core.exceptions import AuthAPIUnavailableError, ServiceEventNotFoundError
from schemas.service_event import EnrichedServiceEvent
from services.fetch_service import fetch_service_event

router = APIRouter()


@router.get(
    "/fetch/{service_event_id}",
    response_model=EnrichedServiceEvent,
    status_code=200,
    responses={
        404: {"description": "No matching record in progress_notes or service_metadata for this service_event_id."},
        502: {"description": "Mock Medicaid authorization API is unreachable or timed out."},
    },
)
async def fetch_event(
    service_event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> EnrichedServiceEvent:
    """
    Input: service_event_id (UUID path parameter).
    Description: Step 1 — fetches and enriches a service event from Pipeline A.
                 Queries progress_notes, service_metadata, and mar tables, then calls
                 the mock Medicaid authorization API to retrieve patient prior auth details.
    Output: 200 EnrichedServiceEvent ready for Step 2 validation.
            404 if service_event_id not found in Pipeline A tables.
            502 if the mock auth API cannot be reached.
    """
    try:
        return await fetch_service_event(
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
