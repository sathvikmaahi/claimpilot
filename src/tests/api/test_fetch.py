"""
API-layer tests for GET /api/v1/fetch/{service_event_id}.

These verify that the route correctly converts service-layer exceptions to HTTP
status codes. Business logic is tested in tests/services/test_fetch_service.py.
  200 — valid session found, auth API responds
  404 — care_session_id not in documented_care_sessions
  502 — auth API unreachable
"""
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient

from api.dependencies import get_db, get_http_client, get_settings
from main import app
from tests.services.conftest import make_db_mock, make_http_mock


class _MockSettings:
    mock_auth_api_url = "http://mock-auth-api"
    auth_api_timeout = 10.0


AUTH_RESPONSE = {
    "patient_prior_auth_number": "AUTH-2026-00101",
    "authorized_units": 96,
    "validity_start_date": "2026-01-01",
    "validity_end_date": "2026-12-31",
    "authorized_service_code": "T2016",
    "waiver_type": "Comprehensive",
}


def _make_session_row(service_event_id: uuid.UUID) -> tuple:
    """Build a (DocumentedCareSession, StaffShiftAssignment, CareRecipient) mock tuple."""
    session = MagicMock()
    session.care_session_id = service_event_id
    session.actual_clock_in_time = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    session.actual_clock_out_time = datetime(2026, 6, 10, 15, 0, 0, tzinfo=timezone.utc)
    session.total_duration_minutes = 480
    session.billable_units_calculated = 32
    session.care_session_narrative = "Assisted with morning ADL routine."
    session.activities_performed = ["morning_adl_routine"]
    session.level_of_support_provided = "verbal_prompts"
    session.recipient_engagement_notes = "Active participation with verbal prompts"
    session.health_observations_notes = None
    session.behavioral_observations_notes = None
    session.community_outing_notes = None
    session.meals_provided = ["breakfast"]
    session.personal_care_activities = ["bathing"]
    session.goals_addressed_in_session = None
    session.checkin_location_latitude = 39.0997
    session.checkin_location_longitude = -94.5786
    session.checkout_location_latitude = 39.0997
    session.checkout_location_longitude = -94.5786
    session.ai_confidence_rating = "High"
    session.documentation_gap_flags = []
    session.dsp_has_signed = True
    session.session_status = "ready_for_billing"
    session.goals_resolution = None

    shift = MagicMock()
    shift.shift_date = date(2026, 6, 10)
    shift.direct_support_professional_name = "Jane Doe"
    shift.service_billing_code = "T2016"

    location = MagicMock()
    location.service_location_name = "Liberty House"
    location.rendering_npi = "1234567890"
    location.modifier_1 = "U1"
    location.modifier_2 = None
    location.modifier_3 = None

    recipient = MagicMock()
    recipient.full_name = "John Smith"
    recipient.medicaid_id = "MO100001"
    recipient.date_of_birth = date(1982, 3, 14)
    recipient.waiver_program = "Comprehensive"
    recipient.primary_diagnosis_code = "F70"
    recipient.sex = "M"

    return (session, shift, location, recipient)


@contextmanager
def _override_deps(db_mock, http_mock):
    """Installs dependency overrides for the duration of one test, then clears them."""
    async def _get_db():
        yield db_mock

    def _get_http():
        return http_mock

    def _get_settings():
        return _MockSettings()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_http_client] = _get_http
    app.dependency_overrides[get_settings] = _get_settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_fetch_returns_200_for_valid_session():
    """
    Input: Valid care_session_id — DB join succeeds, auth API responds.
    Description: Happy path — route returns 200 with a populated EnrichedServiceEvent JSON body.
    Output: 200 with participant_name, procedure_code, and authorization fields populated.
    """
    service_event_id = uuid.uuid4()
    session_row = _make_session_row(service_event_id)
    db_mock = make_db_mock(session_row, mar_pairs=[])
    http_mock = make_http_mock(AUTH_RESPONSE)

    with _override_deps(db_mock, http_mock) as client:
        response = client.get(f"/api/v1/fetch/{service_event_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["participant_name"] == "John Smith"
    assert data["procedure_code"] == "T2016"
    assert data["service_event_id"] == str(service_event_id)
    assert data["authorization"]["patient_prior_auth_number"] == "AUTH-2026-00101"


def test_fetch_returns_404_for_unknown_session_id():
    """
    Input: care_session_id not present in documented_care_sessions.
    Description: Route must convert ServiceEventNotFoundError → HTTP 404.
                 The response detail should contain the requested UUID.
    Output: 404 with service_event_id in the detail message.
    """
    service_event_id = uuid.uuid4()
    db_mock = make_db_mock(session_row=None)
    http_mock = make_http_mock(AUTH_RESPONSE)

    with _override_deps(db_mock, http_mock) as client:
        response = client.get(f"/api/v1/fetch/{service_event_id}")

    assert response.status_code == 404
    assert str(service_event_id) in response.json()["detail"]


def test_fetch_returns_502_when_auth_api_unreachable():
    """
    Input: Valid care_session_id, but auth API raises ConnectError.
    Description: Route must convert AuthAPIUnavailableError → HTTP 502.
                 The response detail should contain the auth API URL.
    Output: 502 with auth API URL in the detail message.
    """
    service_event_id = uuid.uuid4()
    session_row = _make_session_row(service_event_id)
    db_mock = make_db_mock(session_row, mar_pairs=[])
    http_mock = make_http_mock(raise_exc=httpx.ConnectError("Connection refused"))

    with _override_deps(db_mock, http_mock) as client:
        response = client.get(f"/api/v1/fetch/{service_event_id}")

    assert response.status_code == 502
    assert _MockSettings.mock_auth_api_url in response.json()["detail"]
