"""GET /get_roster — today's scheduled recipients for a DSP.

The front door: populates the DSP's pick-a-recipient list. Returns only roster
display fields (who, where, when). The DSP is identified by name for the POC
(no auth yet). Thin adapter over pipeline/db.
"""

from fastapi import APIRouter

from db.db_context import load_roster
from api.model import RosterResponse

router = APIRouter()


@router.get("/get_roster", response_model=RosterResponse)
def get_roster_route(dsp_name: str):
    recipients = load_roster(dsp_name)
    return {"dsp_name": dsp_name, "recipients": recipients}
