"""infra/storage.py — Cloud Storage for uploaded Progress Note photos.

The image pipeline saves every uploaded page to GCS so the original paper form
behind a billed claim is retained and auditable (6-year Medicaid retention).
One note's pages are grouped under a single {upload_id} folder:

    progress-notes/{medicaid_id}/{shift_date}/{upload_id}/page-1.jpg
                                                          /page-2.jpg

Auth is ADC (no keys): storage.Client() picks up the runtime service account on
Cloud Run, or `gcloud auth application-default login` locally. The bucket name
comes from GCS_BUCKET (set in the voice .env), the same os.environ pattern
db_context uses for CLOUD_SQL_*.
"""

import os
import uuid

from google.cloud import storage

from core.observability import get_logger, kv
from core.exceptions import StorageUnavailableError

log = get_logger("infra.storage")

# Lazily-created process-wide client. Built on first use (not at import) so the
# module imports cleanly without credentials/network, mirroring how the rest of
# the app defers its external connections.
_client: storage.Client | None = None

# Map an upload's content-type to the stored object's file extension.
_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "application/pdf": "pdf",
}


def _get_client() -> storage.Client:
    """Return the process-wide Storage client, creating it once via ADC."""
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def _bucket_name() -> str:
    """The target bucket from the environment (clear error if unset)."""
    name = os.environ.get("GCS_BUCKET")
    if not name:
        raise StorageUnavailableError("GCS_BUCKET is not set in the environment.")
    return name


def _ext_for(mime: str) -> str:
    """File extension for a content-type; falls back to 'bin' for unknowns."""
    return _EXT_BY_MIME.get((mime or "").lower(), "bin")


def upload_progress_note_pages(
    medicaid_id: str,
    shift_date: str,
    pages: list[tuple[bytes, str]],
) -> dict:
    """Upload one note's ordered page images to GCS under a single upload folder.

    - medicaid_id / shift_date: organise the object path (queryable by recipient
      and day) — used only for grouping, never trusted for identity.
    - pages: ordered list of (image_bytes, content_type); page 1 first.

    Returns {"upload_id": str, "uris": list[str]} — the gs:// URI of each page,
    in order. The caller (extract_image) returns these so they can later be
    linked to the care session on /submit.

    Raises StorageUnavailableError on any upload failure (no partial-success
    contract — the DSP can simply re-upload).
    """
    upload_id = uuid.uuid4().hex
    bucket_name = _bucket_name()
    prefix = f"progress-notes/{medicaid_id}/{shift_date}/{upload_id}"
    log.info(kv(event="gcs_upload_start", bucket=bucket_name,
                medicaid_id=medicaid_id, pages=len(pages), upload_id=upload_id))

    try:
        bucket = _get_client().bucket(bucket_name)
        uris = []
        for i, (data, mime) in enumerate(pages, start=1):
            object_name = f"{prefix}/page-{i}.{_ext_for(mime)}"
            blob = bucket.blob(object_name)
            blob.metadata = {"medicaid_id": medicaid_id, "upload_id": upload_id, "page": str(i)}
            blob.upload_from_string(data, content_type=mime)
            uris.append(f"gs://{bucket_name}/{object_name}")
            log.info(kv(event="gcs_upload_done", object=object_name, bytes=len(data)))
    except StorageUnavailableError:
        raise
    except Exception as exc:
        log.error(kv(event="gcs_upload_failed", bucket=bucket_name,
                     medicaid_id=medicaid_id, error=type(exc).__name__))
        raise StorageUnavailableError(
            f"Failed to upload Progress Note pages to gs://{bucket_name}/{prefix}"
        ) from exc

    log.info(kv(event="gcs_upload_complete", upload_id=upload_id, pages=len(uris)))
    return {"upload_id": upload_id, "uris": uris}
