"""
API-layer tests for GET /api/v1/claim-builder/{service_event_id}.

These verify that the route correctly wires fetch → agent → EDI generator
and maps exceptions to the right HTTP status codes. The Claim Builder agent
(run_claim_builder) is patched to avoid real Gemini calls.

  200 — fetch + agent succeed; ClaimRead with 837P EDI text returned
  404 — service_event_id not found in documented_care_sessions
  500 — agent fails after retries; claim marked draft_failed
  502 — mock auth API is unreachable
  503 — Cloud SQL query fails
"""
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from agents.claim_builder.agent import ClaimFields
from api.dependencies import get_db, get_http_client, get_settings
from core.exceptions import (
    AuthAPIUnavailableError,
    ClaimBuildError,
    DatabaseUnavailableError,
    ServiceEventNotFoundError,
)
from main import app
from tests.services.conftest import make_db_mock, make_http_mock

_CLAIM_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_EVENT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_NOW = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)

AUTH_RESPONSE = {
    "patient_prior_auth_number": "AUTH-2026-00101",
    "authorized_units": 96,
    "validity_start_date": "2026-01-01",
    "validity_end_date": "2026-12-31",
    "authorized_service_code": "T2016",
    "waiver_type": "Comprehensive",
}

MOCK_FIELDS = ClaimFields(
    subscriber_last_name="Smith",
    subscriber_first_name="John",
    subscriber_medicaid_id="MO100001",
    subscriber_dob="19820314",
    subscriber_sex="M",
    service_date="20260610",
    service_begin_time=None,
    service_end_time=None,
    diagnosis_code="F70",
    diagnosis_qualifier="ABK",
    place_of_service="12",
    claim_filing_indicator="MC",
    rendering_npi="1234567890",
    procedure_code="T2016",
    procedure_qualifier="HC",
    modifier_1="U1",
    modifier_2=None,
    modifier_3=None,
    service_units=32,
    billed_amount="15606.00",
    taxonomy_code="251G00000X",
    notes=None,
)


class _MockSettings:
    mock_auth_api_url = "http://mock-auth-api"
    auth_api_timeout = 10.0
    billing_npi = "1234567890"
    tax_id = "12-3456789"
    payer_id = "MOHLTH"
    t2016_fee_schedule_rate = Decimal("487.68")


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
    session.recipient_engagement_notes = "Active participation"
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


def _make_db_mock_with_claim(service_event_id: uuid.UUID) -> AsyncMock:
    """
    DB mock for the claim builder route.

    Handles the 3 execute() calls from fetch_service_event, plus
    sets claim_id and created_at on flush() — because SQLAlchemy's
    default=uuid.uuid4 runs at real flush time, not at object construction.
    """
    session_row = _make_session_row(service_event_id)
    db = make_db_mock(session_row, mar_pairs=[])

    captured: dict = {}

    def _sync_add(obj) -> None:
        captured["claim"] = obj

    async def _flush() -> None:
        if "claim" in captured:
            captured["claim"].claim_id = _CLAIM_ID
            captured["claim"].created_at = _NOW

    db.add = MagicMock(side_effect=_sync_add)
    db.flush = AsyncMock(side_effect=_flush)
    return db


@contextmanager
def _override_deps(db_mock, http_mock):
    """Install FastAPI dependency overrides for one test, then clear them."""
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


def test_claim_builder_returns_200_with_837p_text():
    """
    Input: Valid service_event_id; agent returns ClaimFields successfully.
    Description: Happy path — fetch succeeds, agent maps fields, EDI is generated.
                 Response must be claim_status=draft with the 837P text in file_837p_reference.
    Output: 200 ClaimRead with claim_id, billed_amount, and ISA/CLM segments in 837P text.
    """
    db_mock = _make_db_mock_with_claim(_EVENT_ID)
    http_mock = make_http_mock(AUTH_RESPONSE)

    with patch("api.routes.claim_builder.run_claim_builder", return_value=MOCK_FIELDS):
        with _override_deps(db_mock, http_mock) as client:
            response = client.post(f"/api/v1/claim-builder/{_EVENT_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["claim_id"] == str(_CLAIM_ID)
    assert data["claim_status"] == "draft"
    assert data["billed_amount"] == "15606.00"
    assert data["file_837p_reference"] is not None
    assert "ISA*" in data["file_837p_reference"]
    assert "CLM*" in data["file_837p_reference"]
    assert "SV1*" in data["file_837p_reference"]


def test_claim_builder_returns_404_for_unknown_session():
    """
    Input: service_event_id not present in documented_care_sessions.
    Description: Route must convert ServiceEventNotFoundError → 404.
                 The response detail must contain the requested UUID.
    Output: 404 with service_event_id in detail.
    """
    with patch(
        "api.routes.claim_builder.fetch_service_event",
        side_effect=ServiceEventNotFoundError(str(_EVENT_ID)),
    ):
        with _override_deps(AsyncMock(), AsyncMock()) as client:
            response = client.post(f"/api/v1/claim-builder/{_EVENT_ID}")

    assert response.status_code == 404
    assert str(_EVENT_ID) in response.json()["detail"]


def test_claim_builder_returns_502_when_auth_api_down():
    """
    Input: DB row found, but mock auth API is unreachable.
    Description: Route must convert AuthAPIUnavailableError → 502.
    Output: 502.
    """
    with patch(
        "api.routes.claim_builder.fetch_service_event",
        side_effect=AuthAPIUnavailableError("http://mock-auth-api unreachable"),
    ):
        with _override_deps(AsyncMock(), AsyncMock()) as client:
            response = client.post(f"/api/v1/claim-builder/{_EVENT_ID}")

    assert response.status_code == 502


def test_claim_builder_returns_503_when_db_unavailable():
    """
    Input: Cloud SQL raises a connection error during fetch.
    Description: Route must convert DatabaseUnavailableError → 503.
    Output: 503.
    """
    with patch(
        "api.routes.claim_builder.fetch_service_event",
        side_effect=DatabaseUnavailableError("Cloud SQL unavailable"),
    ):
        with _override_deps(AsyncMock(), AsyncMock()) as client:
            response = client.post(f"/api/v1/claim-builder/{_EVENT_ID}")

    assert response.status_code == 503


def test_claim_builder_returns_500_and_marks_draft_failed_when_agent_fails():
    """
    Input: Fetch succeeds; Claim Builder agent raises ClaimBuildError after retries.
    Description: Route must catch ClaimBuildError, set claim_status=draft_failed, and return 500.
                 The 500 detail must include the failure message.
    Output: 500 with agent failure reason in detail.
    """
    db_mock = _make_db_mock_with_claim(_EVENT_ID)
    http_mock = make_http_mock(AUTH_RESPONSE)

    with patch(
        "api.routes.claim_builder.run_claim_builder",
        side_effect=ClaimBuildError("Gemini quota exceeded after 3 attempts"),
    ):
        with _override_deps(db_mock, http_mock) as client:
            response = client.post(f"/api/v1/claim-builder/{_EVENT_ID}")

    assert response.status_code == 500
    assert "Gemini quota exceeded" in response.json()["detail"]
