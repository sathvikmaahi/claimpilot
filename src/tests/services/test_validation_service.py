"""
Tests for Step 2 — validate_service_event.

Each test corresponds to one of the 6 mock patients seeded in seed_pipeline_a.py,
plus targeted edge-case tests for EVV missing and field completeness.

Patient scenarios:
  John Smith   (MO100001) — clean pass
  Maria Garcia (MO100002) — CO-151 units exhausted
  David Lee    (MO100003) — CO-197 expired auth
  Susan Brown  (MO100004) — Check 2 service code mismatch
  James Wilson (MO100005) — Check 3 waiver mismatch
  Linda Martinez (MO100006) — clean pass
"""
import pytest
from datetime import date, time
from uuid import uuid4

from schemas.auth import AuthorizationDetails
from schemas.service_event import EnrichedServiceEvent, MARRecord
from services.validation_service import validate_service_event
from core.exceptions import ValidationFailedError


def make_event(**overrides) -> EnrichedServiceEvent:
    """
    Builds a fully valid EnrichedServiceEvent (John Smith clean pass).
    Pass keyword overrides to produce failure scenarios.
    """
    defaults = dict(
        service_event_id=uuid4(),
        participant_name="John Smith",
        participant_dcn="MO100001",
        participant_dob=date(1982, 3, 14),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Liberty House",
        provider_name="Jane Doe",
        provider_signature="jdoe",
        service_description="Assisted with morning ADL routine.",
        activity_time="07:00-15:00",
        participation_level="Active participation with verbal prompts",
        support_level="verbal",
        goals_supported=["morning_adl", "meal_prep"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity=None,
        meal_type="breakfast",
        personal_care_type="bathing",
        evv_checkin_lat=39.0997,
        evv_checkin_lng=-94.5786,
        evv_checkout_lat=39.0997,
        evv_checkout_lng=-94.5786,
        evv_caregiver_id="DSP-001",
        diagnosis_code="F70",
        waiver_identifier="Comprehensive",
        duration_minutes=480,
        service_units=32,
        rendering_npi="1234567890",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None,
        modifier_3=None,
        authorization_number="DSP-AUTH-2026-001",
        flags=[],
        overall_confidence="High",
        mar_records=[],
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2026-00101",
            authorized_units=96,
            validity_start_date=date(2026, 1, 1),
            validity_end_date=date(2026, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Comprehensive",
        ),
    )
    defaults.update(overrides)
    return EnrichedServiceEvent(**defaults)


# --- PASS scenarios ---

async def test_john_smith_clean_pass():
    """
    Input: Valid auth, T2016 code, Comprehensive waiver, EVV present, all fields complete.
    Description: John Smith — clean pass, all 5 checks pass.
    Output: Returns the same EnrichedServiceEvent unchanged.
    """
    event = make_event()
    result = await validate_service_event(event)
    assert result is event


async def test_linda_martinez_clean_pass():
    """
    Input: Valid auth (120 units), T2016, Comprehensive waiver, EVV present.
    Description: Linda Martinez — second clean pass patient.
    Output: Returns the same EnrichedServiceEvent unchanged.
    """
    event = make_event(
        participant_name="Linda Martinez",
        participant_dcn="MO100006",
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2026-00106",
            authorized_units=120,
            validity_start_date=date(2026, 1, 1),
            validity_end_date=date(2026, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Comprehensive",
        ),
    )
    result = await validate_service_event(event)
    assert result is event


# --- Check 1 failures ---

async def test_david_lee_expired_auth():
    """
    Input: Auth validity_end_date=2025-12-31, service_date=2026-06-10.
    Description: David Lee — authorization expired before service date (CO-197).
    Output: ValidationFailedError with check=1 and CO-197 in reason.
    """
    event = make_event(
        participant_name="David Lee",
        participant_dcn="MO100003",
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2025-00103",
            authorized_units=48,
            validity_start_date=date(2025, 1, 1),
            validity_end_date=date(2025, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Comprehensive",
        ),
    )
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 1
    assert "CO-197" in exc_info.value.failures[0].reason


async def test_maria_garcia_units_exhausted():
    """
    Input: authorized_units=0, service_units=32.
    Description: Maria Garcia — authorization units exhausted (CO-151).
    Output: ValidationFailedError with check=1 and CO-151 in reason.
    """
    event = make_event(
        participant_name="Maria Garcia",
        participant_dcn="MO100002",
        service_units=32,
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2026-00102",
            authorized_units=0,
            validity_start_date=date(2026, 1, 1),
            validity_end_date=date(2026, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Comprehensive",
        ),
    )
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 1
    assert "CO-151" in exc_info.value.failures[0].reason


async def test_units_exactly_at_limit_passes():
    """
    Input: authorized_units=32, service_units=32.
    Description: Boundary case — units exactly equal to authorized should pass.
    Output: Returns EnrichedServiceEvent.
    """
    event = make_event(
        service_units=32,
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2026-00101",
            authorized_units=32,
            validity_start_date=date(2026, 1, 1),
            validity_end_date=date(2026, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Comprehensive",
        ),
    )
    result = await validate_service_event(event)
    assert result is event


# --- Check 2 failure ---

async def test_susan_brown_service_code_mismatch():
    """
    Input: procedure_code=T2016, authorized_service_code=T2021.
    Description: Susan Brown — service code mismatch between delivered and authorized service.
    Output: ValidationFailedError with check=2.
    """
    event = make_event(
        participant_name="Susan Brown",
        participant_dcn="MO100004",
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2026-00104",
            authorized_units=64,
            validity_start_date=date(2026, 1, 1),
            validity_end_date=date(2026, 12, 31),
            authorized_service_code="T2021",
            waiver_type="Comprehensive",
        ),
    )
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 2
    assert "T2016" in exc_info.value.failures[0].reason
    assert "T2021" in exc_info.value.failures[0].reason


# --- Check 3 failure ---

async def test_james_wilson_waiver_mismatch():
    """
    Input: auth API waiver_type='Partnership for Hope', T2016 requires 'Comprehensive'.
    Description: James Wilson — waiver mismatch, T2016 ISL not covered under Partnership for Hope.
    Output: ValidationFailedError with check=3.
    """
    event = make_event(
        participant_name="James Wilson",
        participant_dcn="MO100005",
        waiver_identifier="Partnership for Hope",
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2026-00105",
            authorized_units=80,
            validity_start_date=date(2026, 1, 1),
            validity_end_date=date(2026, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Partnership for Hope",
        ),
    )
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 3
    assert "Partnership for Hope" in exc_info.value.failures[0].reason
    assert "Comprehensive" in exc_info.value.failures[0].reason


# --- Check 4 failure ---

async def test_evv_missing_checkin():
    """
    Input: evv_checkin_lat=None.
    Description: EVV check-in GPS coordinate missing.
    Output: ValidationFailedError with check=4.
    """
    event = make_event(evv_checkin_lat=None)
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 4


async def test_evv_missing_checkout():
    """
    Input: evv_checkout_lat=None, evv_checkout_lng=None.
    Description: EVV check-out GPS coordinates missing.
    Output: ValidationFailedError with check=4.
    """
    event = make_event(evv_checkout_lat=None, evv_checkout_lng=None)
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 4


# --- Check 5 failure ---

async def test_field_completeness_missing_npi():
    """
    Input: rendering_npi="" (blank).
    Description: Rendering NPI blank — required on 837P loop 2310B.
    Output: ValidationFailedError with check=5 and 'Rendering NPI' in reason.
    """
    event = make_event(rendering_npi="")
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 5
    assert "Rendering NPI" in exc_info.value.failures[0].reason


async def test_field_completeness_missing_signature():
    """
    Input: provider_signature="" (blank).
    Description: DSP signature blank — legally required per 13 CSR 70-3.030.
    Output: ValidationFailedError with check=5 and 'DSP signature' in reason.
    """
    event = make_event(provider_signature="")
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 5
    assert "DSP signature" in exc_info.value.failures[0].reason


async def test_field_completeness_multiple_missing():
    """
    Input: rendering_npi="" and participant_dcn="" (both blank).
    Description: Multiple required fields blank — all should be listed in the reason.
    Output: ValidationFailedError with check=5 listing both missing fields.
    """
    event = make_event(rendering_npi="", participant_dcn="")
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    assert exc_info.value.failures[0].check == 5
    assert "Rendering NPI" in exc_info.value.failures[0].reason
    assert "DCN" in exc_info.value.failures[0].reason


async def test_multiple_checks_fail_all_returned():
    """
    Input: Expired auth + EVV missing + NPI blank — 3 independent failures.
    Description: Verifies that all failures are collected and returned in one raise,
                 not just the first one. Check 1b (units) is skipped since auth is expired.
    Output: ValidationFailedError with 3 failures: check 1 (CO-197), check 4, check 5.
    """
    event = make_event(
        evv_checkin_lat=None,
        rendering_npi="",
        authorization=AuthorizationDetails(
            patient_prior_auth_number="AUTH-2025-00103",
            authorized_units=48,
            validity_start_date=date(2025, 1, 1),
            validity_end_date=date(2025, 12, 31),
            authorized_service_code="T2016",
            waiver_type="Comprehensive",
        ),
    )
    with pytest.raises(ValidationFailedError) as exc_info:
        await validate_service_event(event)

    checks = [f.check for f in exc_info.value.failures]
    assert 1 in checks  # expired auth CO-197
    assert 4 in checks  # EVV missing
    assert 5 in checks  # NPI blank
    assert len(exc_info.value.failures) == 3
