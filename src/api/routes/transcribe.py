"""POST /transcribe — stateless speech->text for voice notes.

Audio in (multipart), plain text out. No DB, no goals, no session — the
frontend calls this per voice note, shows the text for confirm/retake, and the
confirmed text later rides into /submit inside goals_resolution. Thin adapter.
"""

from fastapi import APIRouter, UploadFile, File

from services.pipeline import transcribe
from api.model import TranscribeResponse

router = APIRouter()


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_route(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    transcript = await transcribe(audio_bytes)
    return {"transcript": transcript}
