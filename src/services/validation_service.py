"""
Step 2: Validate.

Input: EnrichedServiceEvent from Step 1 (Fetch).
Description: Runs 5 validation checks against the enriched service event and collects
             ALL failures before raising, so the clerk sees every issue in one response.
             Check 1a — Auth not expired: service_date falls within validity_start_date..validity_end_date.
             Check 1b — Units not exhausted: service_units <= authorized_units (CO-151).
                        Skipped if 1a fails — units check against an expired auth is meaningless.
             Check 2  — Service tag: procedure_code matches authorized_service_code from auth API.
             Check 3  — Waiver type: auth API waiver_type is 'Comprehensive' (required for T2016 ISL).
             Check 4  — EVV verification: all 4 GPS coordinates are present.
             Check 5  — Field completeness: all required 837P fields are non-null.
             PASS → returns validated event, caller routes to Step 3 (Claim Builder).
             FAIL → raises ValidationFailedError carrying the full list of failures.
Output: EnrichedServiceEvent (pass-through) on success, ValidationFailedError on failure.
"""
from schemas.service_event import EnrichedServiceEvent
from core.exceptions import ValidationFailedError, ValidationFailure

REQUIRED_WAIVER = "Comprehensive"

# (field_name, display_label) — all required on the 837P
_REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("rendering_npi", "Rendering NPI"),
    ("participant_dcn", "DCN"),
    ("procedure_code", "Procedure code"),
    ("service_units", "Service units"),
    ("service_date", "Service date"),
    ("provider_signature", "DSP signature"),
]


def compute_validation_results(event: EnrichedServiceEvent) -> list[dict]:
    """
    Runs all 5 checks and returns structured results for storage on the claim row.
    Does not raise — captures pass/fail + key value for every check.
    Check 1b is marked skipped (passed=None) when 1a fails, matching validate logic.
    """
    auth = event.authorization
    results: list[dict] = []

    # Check 1a — Auth not expired
    auth_date_valid = auth.validity_start_date <= event.service_date <= auth.validity_end_date
    results.append({
        "check": "1a",
        "label": "Auth not expired",
        "passed": auth_date_valid,
        "value": f"{auth.validity_start_date} – {auth.validity_end_date}",
    })

    # Check 1b — Units not exhausted (skipped if 1a failed)
    if auth_date_valid:
        units_ok = event.service_units <= auth.authorized_units
        results.append({
            "check": "1b",
            "label": "Units not exhausted",
            "passed": units_ok,
            "value": f"{event.service_units} of {auth.authorized_units} authorized",
        })
    else:
        results.append({
            "check": "1b",
            "label": "Units not exhausted",
            "passed": None,
            "value": "Skipped — auth expired",
        })

    # Check 2 — Service code matches auth
    code_match = event.procedure_code == auth.authorized_service_code
    results.append({
        "check": "2",
        "label": "Service code matches auth",
        "passed": code_match,
        "value": (
            f"{event.procedure_code} ✓"
            if code_match
            else f"Delivered {event.procedure_code}, authorized {auth.authorized_service_code}"
        ),
    })

    # Check 3 — Comprehensive enrollment
    waiver_ok = auth.waiver_type == REQUIRED_WAIVER
    results.append({
        "check": "3",
        "label": "Comprehensive enrollment",
        "passed": waiver_ok,
        "value": auth.waiver_type,
    })

    # Check 4 — EVV GPS present
    evv = [event.evv_checkin_lat, event.evv_checkin_lng, event.evv_checkout_lat, event.evv_checkout_lng]
    evv_ok = all(c is not None for c in evv)
    results.append({
        "check": "4",
        "label": "EVV GPS present",
        "passed": evv_ok,
        "value": (
            f"In {event.evv_checkin_lat}° N {event.evv_checkin_lng}° W / "
            f"Out {event.evv_checkout_lat}° N {event.evv_checkout_lng}° W"
            if evv_ok else "Check-in or check-out GPS coordinates missing"
        ),
    })

    # Check 5 — 837P field completeness
    missing = [label for field, label in _REQUIRED_FIELDS if not getattr(event, field, None)]
    results.append({
        "check": "5",
        "label": "837P fields complete",
        "passed": not missing,
        "value": "All required fields present" if not missing else f"Missing: {', '.join(missing)}",
    })

    return results


async def validate_service_event(event: EnrichedServiceEvent) -> EnrichedServiceEvent:
    """
    Input: EnrichedServiceEvent produced by Step 1.
    Description: Runs all 5 validation checks and collects every failure before raising.
                 Check 1b is skipped when 1a fails — units are irrelevant against an expired auth.
                 Checks 2-5 are always run regardless of other failures.
    Output: The same EnrichedServiceEvent unchanged on full pass.
    """
    auth = event.authorization
    failures: list[ValidationFailure] = []

    # Check 1a — Authorization not expired (CO-197)
    auth_date_valid = auth.validity_start_date <= event.service_date <= auth.validity_end_date
    if not auth_date_valid:
        failures.append(ValidationFailure(
            check=1,
            reason=(
                f"Patient authorization is expired — service date {event.service_date} "
                f"falls outside authorized period "
                f"{auth.validity_start_date} to {auth.validity_end_date} (CO-197)"
            ),
        ))

    # Check 1b — Authorization units not exhausted (CO-151)
    # Skipped if auth is expired — units check against an expired auth is meaningless
    if auth_date_valid and event.service_units > auth.authorized_units:
        failures.append(ValidationFailure(
            check=1,
            reason=(
                f"Patient authorization units exhausted — "
                f"{event.service_units} units requested, "
                f"{auth.authorized_units} remaining (CO-151)"
            ),
        ))

    # Check 2 — Service code matches authorization
    if event.procedure_code != auth.authorized_service_code:
        failures.append(ValidationFailure(
            check=2,
            reason=(
                f"Service code mismatch — delivered {event.procedure_code}, "
                f"authorized for {auth.authorized_service_code}"
            ),
        ))

    # Check 3 — Individual enrolled in Comprehensive Waiver (required for T2016 ISL)
    if auth.waiver_type != REQUIRED_WAIVER:
        failures.append(ValidationFailure(
            check=3,
            reason=(
                f"Waiver mismatch — individual enrolled in '{auth.waiver_type}', "
                f"T2016 ISL requires '{REQUIRED_WAIVER}'"
            ),
        ))

    # Check 4 — EVV GPS coordinates present
    # Geo-fence radius check requires ISL home coordinate config — open item (DSP_Research open item 4)
    evv_fields = [
        event.evv_checkin_lat,
        event.evv_checkin_lng,
        event.evv_checkout_lat,
        event.evv_checkout_lng,
    ]
    if any(coord is None for coord in evv_fields):
        failures.append(ValidationFailure(
            check=4,
            reason="EVV data missing — check-in or check-out GPS coordinates not recorded",
        ))

    # Check 5 — All required 837P fields present
    missing = [label for field, label in _REQUIRED_FIELDS if not getattr(event, field, None)]
    if missing:
        failures.append(ValidationFailure(
            check=5,
            reason=f"Missing required fields: {', '.join(missing)}",
        ))

    if failures:
        raise ValidationFailedError(failures)

    return event
