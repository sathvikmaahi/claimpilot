"""Pydantic request/response models shared by the API routes.

These describe the HTTP contract — what the frontend receives and sends.
They are intentionally permissive about the inner shape of progress_note /
mar_scaffold (dict / list[dict]) because those are produced and consumed by
pipeline.py, which owns their structure. The models pin the OUTER envelope.
"""

from pydantic import BaseModel


class ExtractResponse(BaseModel):
    """What POST /extract returns: the blocks the frontend renders."""
    auto_fields: dict          # header the form pre-fills (name, DOB, hours, ...)
    progress_note: dict        # the LLM-authored editable note
    mar_scaffold: list[dict]   # the DB-prefilled med grid the DSP taps
    active_goals: list[dict]   # every active goal, for the resolution checklist
 
    
    
    
class SubmitRequest(BaseModel):
    """What POST /submit receives: the DSP-approved note, MAR taps, and signature data.

    Inner shapes (progress_note, mar_grid items) are owned by pipeline.py and
    validated lightly here — the model pins the envelope, the library owns the
    contents. This matches the roadmap's 'validate lightly' for /submit.
    """
    medicaid_id: str
    progress_note: dict          # the edited note (same shape as extract's progress_note)
    mar_grid: list[dict] = []    # the DSP's per-med taps; empty if no in-window meds
    meals: list[str] = []        # tap-only (form S10), never voiced
    personal_care: list[str] = []  # tap-only (form S11), never voiced
    goals_resolution: list[dict] = []  # per-goal decision [{goal_id, addressed, note}]


class SubmitResponse(BaseModel):
    """What POST /submit returns after the atomic note + MAR write."""
    care_session_id: str
    mar_rows_written: int
    
    
class TranscribeResponse(BaseModel):
    """What POST /transcribe returns: the transcribed text, nothing else."""
    transcript: str

class RosterResponse(BaseModel):
    """What GET /get_roster returns: the DSP and their today recipients."""
    dsp_name: str
    recipients: list[dict]   # each: recipient_name, medicaid_id, location, hours
