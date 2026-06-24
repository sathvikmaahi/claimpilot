"""POST /transcribe — stateless speech->text for voice notes.

Audio in (multipart), plain text out. No DB, no goals, no session — the
frontend calls this per voice note, shows the text for confirm/retake, and the
confirmed text later rides into /submit inside goals_resolution. Thin adapter.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException

from services.pipeline import transcribe
from api.model import TranscribeResponse
from core.observability import get_logger, kv

log = get_logger("api.transcribe")
router = APIRouter()


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_route(audio: UploadFile = File(...)):
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe(audio_bytes)
        return {"transcript": transcript}
    except Exception as exc:
        log.error(kv(event="transcribe_failed", error=type(exc).__name__))
        raise HTTPException(status_code=500, detail="Failed to transcribe the audio.") from exc
