from datetime import date, time
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest


@pytest.fixture
def service_event_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_progress_note(service_event_id: UUID) -> MagicMock:
    note = MagicMock()
    note.service_event_id = service_event_id
    note.participant_name = "John Smith"
    note.participant_dcn = "MO100001"
    note.participant_dob = date(1982, 3, 14)
    note.service_date = date(2026, 6, 10)
    note.begin_time = time(7, 0, 0)
    note.end_time = time(15, 0, 0)
    note.service_location = "Liberty House"
    note.provider_name = "Jane Doe"
    note.provider_signature = "jdoe"
    note.service_description = "Assisted with morning ADL routine."
    note.activity_time = "07:00-15:00"
    note.participation_level = "Active participation with verbal prompts"
    note.support_level = "verbal"
    note.goals_supported = ["morning_adl", "meal_prep"]
    note.activity_category = "Residential Habilitation"
    note.health_observations = None
    note.behavioral_notes = None
    note.community_activity = None
    note.meal_type = "breakfast"
    note.personal_care_type = "bathing"
    return note


@pytest.fixture
def mock_service_meta(service_event_id: UUID) -> MagicMock:
    meta = MagicMock()
    meta.service_event_id = service_event_id
    meta.evv_checkin_lat = 39.0997
    meta.evv_checkin_lng = -94.5786
    meta.evv_checkout_lat = 39.0997
    meta.evv_checkout_lng = -94.5786
    meta.evv_caregiver_id = "DSP-001"
    meta.diagnosis_code = "F70"
    meta.waiver_identifier = "Comprehensive"
    meta.duration_minutes = 480
    meta.service_units = 32
    meta.rendering_npi = "1234567890"
    meta.procedure_code = "T2016"
    meta.modifier_1 = "UP"
    meta.modifier_2 = None
    meta.modifier_3 = None
    meta.authorization_number = "DSP-AUTH-2026-001"
    meta.flags = []
    meta.overall_confidence = "High"
    return meta


@pytest.fixture
def mock_mar_record(service_event_id: UUID) -> MagicMock:
    mar = MagicMock()
    mar.id = uuid4()
    mar.service_event_id = service_event_id
    mar.med_name = "Metformin"
    mar.med_dosage = "500mg"
    mar.med_time_administered = time(8, 0, 0)
    mar.variance_code = None
    return mar


@pytest.fixture
def auth_response_data() -> dict:
    return {
        "patient_prior_auth_number": "AUTH-2026-00101",
        "authorized_units": 96,
        "validity_start_date": "2026-01-01",
        "validity_end_date": "2026-12-31",
        "authorized_service_code": "T2016",
        "waiver_type": "Comprehensive",
    }


def make_db_mock(
    progress_note=None,
    service_meta=None,
    mar_records: list | None = None,
) -> AsyncMock:
    """
    Builds a mock AsyncSession whose execute() returns different results per call:
    call 1 → progress_notes result
    call 2 → service_metadata result
    call 3 → MAR result
    """
    db = AsyncMock()

    result_pn = MagicMock()
    result_pn.scalar_one_or_none.return_value = progress_note

    result_sm = MagicMock()
    result_sm.scalar_one_or_none.return_value = service_meta

    result_mar = MagicMock()
    result_mar.scalars.return_value.all.return_value = mar_records or []

    db.execute.side_effect = [result_pn, result_sm, result_mar]
    return db


def make_http_mock(response_data: dict | None = None, raise_exc: Exception | None = None) -> AsyncMock:
    """
    Builds a mock httpx.AsyncClient.
    If raise_exc is set, post() raises that exception.
    Otherwise post() returns a mock response with the given JSON data.
    """
    client = AsyncMock()
    if raise_exc is not None:
        client.post.side_effect = raise_exc
    else:
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()
        client.post.return_value = mock_response
    return client
