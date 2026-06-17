"""
Stub — Step 2: Validate.

Input: EnrichedServiceEvent from Step 1 (Fetch).
Description: Runs 5 sequential validation checks against the enriched service event.
             Check 1 — Authorization valid: patient prior auth is active, not expired, covers this service date.
             Check 2 — Service tag: procedure_code T2016 matches the authorized_service_code from the auth API.
             Check 3 — Waiver type: waiver_identifier matches the waiver_type returned by the auth API.
             Check 4 — EVV verification: EVV GPS coordinates are present and within geo-fence of the ISL home.
             Check 5 — Field completeness: all required 837P fields are non-null (NPI, DCN, procedure code, units, date, signature).
             PASS → returns validated event, caller routes to Step 3 (Claim Builder).
             FAIL → raises ValidationFailedError with specific check number and failure message for clerk display.
Output: EnrichedServiceEvent (pass-through) on success, ValidationFailedError on failure.
"""
from schemas.service_event import EnrichedServiceEvent
from core.exceptions import ValidationFailedError


async def validate_service_event(event: EnrichedServiceEvent) -> EnrichedServiceEvent:
    raise NotImplementedError("Step 2 validation not yet implemented.")
