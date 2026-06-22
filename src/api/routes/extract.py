"""POST /extract — the read path over HTTP.

Receives the DSP's narration (and optional toggled-observation clips) as
multipart file uploads, reads their bytes, and hands them to the verified
pipeline.extract(). No business logic lives here — this is a thin HTTP adapter.
"""

from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

from services.pipeline import extract
from api.model import ExtractResponse

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
    result = await extract(
        medicaid_id=medicaid_id,
        narration_activities=activities_bytes,
        narration_engagement=engagement_bytes,
        toggled=toggled,
    )
    return result
