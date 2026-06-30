"""POST /submit — the write path over HTTP.

Receives the DSP-approved note + MAR taps as JSON, folds in medicaid_id, and
hands everything to the verified pipeline.write_session(), which writes the
progress note and MAR rows in one atomic transaction. Thin HTTP adapter — the
atomicity and UUID-resolution all live in pipeline.py.
"""

from fastapi import APIRouter, HTTPException

from services.pipeline import write_session, IncompleteGoals
from db.db_context import NoShiftToday, RecipientNotFound
from api.model import SubmitRequest, SubmitResponse
from core.observability import get_logger, kv

log = get_logger("api.submit")
router = APIRouter()


@router.post("/submit", response_model=SubmitResponse)
def submit_route(req: SubmitRequest):
    # The library expects medicaid_id inside the approved note (so it can
    # re-derive FKs / goal UUIDs / med IDs from the DB). The route carries it
    # as a top-level field for the frontend's convenience; fold it in here.
    approved = dict(req.progress_note)
    approved["medicaid_id"] = req.medicaid_id

    # Call the verified atomic writer. Note + MAR commit together or not at all.
    try:
        return write_session(
            approved,
            mar_grid=req.mar_grid,
            meals=req.meals,
            personal_care=req.personal_care,
            goals_resolution=req.goals_resolution,
            source_image_uris=req.source_image_uris,
        )
    except IncompleteGoals as exc:
        # Incomplete goal resolution from the client -> actionable 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RecipientNotFound, NoShiftToday) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.error(kv(event="submit_failed", medicaid_id=req.medicaid_id, error=type(exc).__name__))
        raise HTTPException(status_code=500, detail="Failed to write the care session.") from exc