"""
Process Claims route — POST /api/v1/process-claims

Input: None (no request body).
Description: Finds all documented_care_sessions that have no claims row yet,
             runs Fetch → Validate → Claim Builder for each.
             PASS → draft claim (Ready to Review queue).
             FAIL → failed claim (Needs Attention queue).
Output: ProcessClaimsResult { processed, draft, failed }
"""
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_http_client, get_settings
from core.config import Settings
from schemas.claim import ProcessClaimsResult
from services.process_claims_service import process_all_claims

router = APIRouter()


@router.post(
    "/process-claims",
    response_model=ProcessClaimsResult,
    status_code=200,
)
async def process_claims(
    db: AsyncSession = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> ProcessClaimsResult:
    return await process_all_claims(db=db, http_client=http_client, settings=settings)
