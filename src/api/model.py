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


class ImageExtractResponse(ExtractResponse):
    """What POST /extract_image returns: the same four blocks as /extract, plus
    the fields only the photographed form carries. meals/personal_care are the
    S10/S11 checkbox pre-fills the DSP confirms; source_image_uris are the stored
    page photos, carried to /submit so the saved claim points at its source form.
    """
    meals: list[str] = []              # pre-filled from S10 checkboxes (DSP confirms)
    personal_care: list[str] = []      # pre-filled from S11 checkboxes (DSP confirms)
    source_image_uris: list[str] = []  # gs:// URIs of the stored pages, in order
    extraction_failed: bool = False    # true if the vision read failed; pages are
                                       # saved and the DSP fills the form manually

    
    
    
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
    source_image_uris: list[str] = []  # gs:// URIs from /extract_image; empty for voice


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
