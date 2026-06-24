"""POST /extract — the read path over HTTP.

Receives the DSP's narration (and optional toggled-observation clips) as
multipart file uploads, reads their bytes, and hands them to the verified
pipeline.extract(). No business logic lives here — this is a thin HTTP adapter.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from services.pipeline import extract
from db.db_context import NoShiftToday, RecipientNotFound
from api.model import ExtractResponse
from core.observability import get_logger, kv

log = get_logger("api.extract")
router = APIRouter()


@router.post("/extract", response_model=ExtractResponse)
async def extract_route(
    medicaid_id: str = Form(...),
    narration_activities: UploadFile = File(...),
    narration_engagement: Optional[UploadFile] = File(None),
    health: Optional[UploadFile] = File(None),
    behavioral: Optional[UploadFile] = File(None),
    outing: Optional[UploadFile] = File(None),
):
    try:
        # 1. Read the required narration bytes off the upload.
        activities_bytes = await narration_activities.read()
        engagement_bytes = await narration_engagement.read() if narration_engagement else None

        # 2. Build the toggled-observations dict from whichever clips were sent.
        #    A toggle that wasn't uploaded simply isn't in the dict (stays null downstream).
        toggled = {}
        for field, upload in (("health", health), ("behavioral", behavioral), ("outing", outing)):
            if upload is not None:
                toggled[field] = await upload.read()

        # 3. Call the verified library. The route adds nothing but unwrapping.
        return await extract(
            medicaid_id=medicaid_id,
            narration_activities=activities_bytes,
            narration_engagement=engagement_bytes,
            toggled=toggled,
        )
    except (RecipientNotFound, NoShiftToday) as exc:
        # Expected "no data for this recipient today" conditions -> 404.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        # Unexpected (LLM/DB/processing) failure -> clean 500, logged (no stack trace leaked).
        log.error(kv(event="extract_failed", medicaid_id=medicaid_id, error=type(exc).__name__))
        raise HTTPException(status_code=500, detail="Failed to extract the care session from the narration.") from exc
