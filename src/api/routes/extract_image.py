"""POST /extract_image — the image read path over HTTP.

Receives the photographed Progress Note as an ordered list of image uploads
plus the chosen medicaid_id, reads their bytes (preserving page order), and
hands them to the verified pipeline.extract_image(). Thin HTTP adapter — the
extraction, GCS storage, and the graceful no-extraction fallback (option A)
all live in pipeline.py.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from services.pipeline import extract_image
from db.db_context import NoShiftToday, RecipientNotFound
from core.exceptions import StorageUnavailableError
from api.model import ImageExtractResponse
from core.observability import get_logger, kv

log = get_logger("api.extract_image")
router = APIRouter()


@router.post("/extract_image", response_model=ImageExtractResponse)
async def extract_image_route(
    medicaid_id: str = Form(...),
    pages: list[UploadFile] = File(...),
):
    try:
        # Read each page's bytes + content-type, preserving upload order.
        page_data = []
        for page in pages:
            page_data.append((await page.read(), page.content_type or "image/jpeg"))

        # Call the verified library. Storage + extraction + the manual-entry
        # fallback all happen inside; the route only unwraps the upload.
        return await extract_image(medicaid_id=medicaid_id, pages=page_data)
    except (RecipientNotFound, NoShiftToday) as exc:
        # Expected "no data for this recipient today" conditions -> 404.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StorageUnavailableError as exc:
        # The pages could not be saved -> upstream dependency failure (GCS).
        log.error(kv(event="extract_image_failed", medicaid_id=medicaid_id, error=type(exc).__name__))
        raise HTTPException(status_code=502, detail="Couldn't save the uploaded photos. Please try again.") from exc
    except Exception as exc:
        # Unexpected failure -> clean 500, logged (no stack trace leaked).
        log.error(kv(event="extract_image_failed", medicaid_id=medicaid_id, error=type(exc).__name__))
        raise HTTPException(status_code=500, detail="Failed to process the uploaded form.") from exc
