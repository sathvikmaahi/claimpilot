"""Integration tests for the image pipeline (live Gemini + GCS + Cloud SQL).

Opt-in via `-m integration`. Skipped cleanly when the sample form photos or
Cloud SQL creds are absent (the photos are gitignored, present only on a machine
set up to run this — mirroring how the voice write-path test skips on a missing
audio fixture).
"""

import os
import sys
import asyncio
import mimetypes
import pytest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", ".."))

from services.pipeline import extract_image, write_session
from db.db_context import _connect, load_context, delete_care_session

LINDA_MEDICAID_ID = "517402981"

_SAMPLE_DIR = os.path.join(here, "..", "..", "scripts", "sample_pages_")
_PAGES = [os.path.join(_SAMPLE_DIR, f"page_{n}.jpg") for n in (1, 2, 3)]

_have_pages = all(os.path.exists(p) for p in _PAGES)
_have_db = bool(os.environ.get("CLOUD_SQL_HOST"))


def _read_pages():
    pages = []
    for p in _PAGES:
        with open(p, "rb") as f:
            pages.append((f.read(), mimetypes.guess_type(p)[0] or "image/jpeg"))
    return pages


def _delete_gcs_upload(uris):
    """Remove the stored test pages so the bucket stays clean after the test."""
    if not uris:
        return
    from google.cloud import storage
    bucket_name, _, obj = uris[0][len("gs://"):].partition("/")
    prefix = obj.rsplit("/", 1)[0]  # the {upload_id} folder shared by all pages
    client = storage.Client()
    for blob in client.list_blobs(bucket_name, prefix=prefix):
        blob.delete()


@pytest.mark.integration
@pytest.mark.skipif(
    not (_have_pages and _have_db),
    reason="integration prerequisites missing (sample photos or Cloud SQL creds)",
)
def test_extract_image_live():
    """Live: extract_image over 3 sample pages -> blocks present, voice-shaped note, pages stored."""
    uris = []
    try:
        res = asyncio.run(extract_image(LINDA_MEDICAID_ID, _read_pages()))
        uris = res["source_image_uris"]

        assert res["extraction_failed"] is False
        assert len(uris) == 3, "all 3 pages should be stored in GCS"
        # progress_note matches the voice shape so /submit consumes it unchanged.
        assert "extracted_fields_section2" in res["progress_note"]
        assert isinstance(res["progress_note"]["transcript"], str)
        assert len(res["active_goals"]) >= 1, "active goals should be returned for resolution"
    finally:
        _delete_gcs_upload(uris)


@pytest.mark.integration
@pytest.mark.skipif(not _have_db, reason="Cloud SQL creds missing")
def test_source_image_uris_linkage():
    """write_session stores source_image_uris for an image note and NULL for voice."""
    ctx = load_context(LINDA_MEDICAID_ID)
    goals_resolution = [{"goal_id": str(g["goal_id"]), "addressed": True} for g in ctx["goals_raw"]]

    def approved():
        return {
            "medicaid_id": LINDA_MEDICAID_ID, "transcript": "linkage test",
            "activities_performed": ["bath"], "support_level": "verbal",
            "individual_response": "ok",
            "extracted_fields_section2": {
                "health_observations": None, "behavioral_observations": None, "community_outing": None,
            },
            "gaps_detected": [], "confidence": {"activities_performed": 0.9},
        }

    img_id = voi_id = None
    try:
        uris = ["gs://b/x/page-1.jpg", "gs://b/x/page-2.jpg"]
        img_id = write_session(approved(), goals_resolution=goals_resolution, source_image_uris=uris)["care_session_id"]
        voi_id = write_session(approved(), goals_resolution=goals_resolution)["care_session_id"]

        conn = _connect()
        cur = conn.cursor()
        cur.execute("select source_image_uris from documented_care_sessions where care_session_id=%s", (img_id,))
        assert cur.fetchone()[0] == uris, "image note should store the source URIs"
        cur.execute("select source_image_uris from documented_care_sessions where care_session_id=%s", (voi_id,))
        assert cur.fetchone()[0] is None, "voice note should leave source_image_uris NULL"
        cur.close()
        conn.close()
    finally:
        if img_id:
            delete_care_session(img_id)
        if voi_id:
            delete_care_session(voi_id)
