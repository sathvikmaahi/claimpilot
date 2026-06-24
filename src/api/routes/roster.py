"""GET /get_roster — today's scheduled recipients for a DSP.

The front door: populates the DSP's pick-a-recipient list. Returns only roster
display fields (who, where, when). The DSP is identified by name for the POC
(no auth yet). Thin adapter over pipeline/db.
"""

from fastapi import APIRouter, HTTPException

from db.db_context import load_roster
from api.model import RosterResponse
from core.observability import get_logger, kv

log = get_logger("api.roster")
router = APIRouter()


@router.get("/get_roster", response_model=RosterResponse)
def get_roster_route(dsp_name: str):
    try:
        recipients = load_roster(dsp_name)
        return {"dsp_name": dsp_name, "recipients": recipients}
    except Exception as exc:
        log.error(kv(event="roster_failed", dsp_name=dsp_name, error=type(exc).__name__))
        raise HTTPException(status_code=500, detail="Failed to load the roster.") from exc
