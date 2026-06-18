"""Pydantic request/response models shared by the API routes.

These describe the HTTP contract — what the frontend receives and sends.
They are intentionally permissive about the inner shape of progress_note /
mar_scaffold (dict / list[dict]) because those are produced and consumed by
pipeline.py, which owns their structure. The models pin the OUTER envelope.
"""

from pydantic import BaseModel


class ExtractResponse(BaseModel):
    """What POST /extract returns: the three blocks the frontend renders."""
    auto_fields: dict          # header the form pre-fills (name, DOB, hours, ...)
    progress_note: dict        # the LLM-authored editable note
    mar_scaffold: list[dict]   # the DB-prefilled med grid the DSP taps