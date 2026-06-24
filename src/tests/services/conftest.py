from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest


@pytest.fixture
def service_event_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_session(service_event_id: UUID) -> MagicMock:
    """Mock DocumentedCareSession ORM object returned as part of the main joined query."""
    s = MagicMock()
    s.care_session_id = service_event_id
    s.actual_clock_in_time = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    s.actual_clock_out_time = datetime(2026, 6, 10, 15, 0, 0, tzinfo=timezone.utc)
    s.total_duration_minutes = 480
    s.billable_units_calculated = 32
    s.care_session_narrative = "Assisted with morning ADL routine."
    s.activities_performed = ["morning_adl_routine", "breakfast_preparation"]
    s.level_of_support_provided = "verbal_prompts"
    s.recipient_engagement_notes = "Active participation with verbal prompts"
    s.health_observations_notes = None
    s.behavioral_observations_notes = None
    s.community_outing_notes = None
    s.meals_provided = ["breakfast"]
    s.personal_care_activities = ["bathing"]
    s.goals_addressed_in_session = None   # None → goals query is skipped in fetch service
    s.checkin_location_latitude = 39.0997
    s.checkin_location_longitude = -94.5786
    s.checkout_location_latitude = 39.0997
    s.checkout_location_longitude = -94.5786
    s.ai_confidence_rating = "High"
    s.documentation_gap_flags = []
    s.dsp_has_signed = True
    s.session_status = "ready_for_billing"
    s.goals_resolution = None
    return s


@pytest.fixture
def mock_shift() -> MagicMock:
    """Mock StaffShiftAssignment ORM object returned as part of the main joined query."""
    s = MagicMock()
    s.shift_date = date(2026, 6, 10)
    s.service_location_name = "Liberty House"
    s.direct_support_professional_name = "Jane Doe"
    s.service_billing_code = "T2016"
    return s


@pytest.fixture
def mock_recipient() -> MagicMock:
    """Mock CareRecipient ORM object returned as part of the main joined query."""
    r = MagicMock()
    r.full_name = "John Smith"
    r.medicaid_id = "MO100001"
    r.date_of_birth = date(1982, 3, 14)
    r.waiver_program = "Comprehensive"
    r.primary_diagnosis_code = "F70"
    return r


@pytest.fixture
def mock_mar_pair(service_event_id: UUID) -> tuple:
    """Mock (MedicationAdministrationRecord, PrescribedMedication) row from the MAR joined query."""
    mar = MagicMock()
    mar.administration_record_id = uuid4()
    mar.care_session_id = service_event_id
    mar.was_medication_given = True
    mar.actual_administration_time = datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc)
    mar.reason_if_not_given = None

    med = MagicMock()
    med.medication_name = "Metformin"
    med.dosage_amount = "500mg"

    return (mar, med)


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
    session_row=None,
    has_goals: bool = False,
    goal_descriptions: list[str] | None = None,
    mar_pairs: list | None = None,
) -> AsyncMock:
    """
    Builds a mock AsyncSession whose execute() side_effect matches the fetch service's
    3-query pattern:
      call 1 → main joined query → one_or_none() returns session_row (tuple or None)
      call 2 → goals query       → scalars().all() (only when has_goals=True)
      call 2/3 → MAR joined query → all() returns mar_pairs list

    Pass has_goals=True when mock_session.goals_addressed_in_session is truthy,
    so the side_effect list includes the goals result at the right position.
    """
    db = AsyncMock()
    side_effects = []

    # Call 1: main joined query
    result_main = MagicMock()
    result_main.one_or_none.return_value = session_row
    side_effects.append(result_main)

    if session_row is not None:
        if has_goals:
            result_goals = MagicMock()
            result_goals.scalars.return_value.all.return_value = goal_descriptions or []
            side_effects.append(result_goals)

        result_mar = MagicMock()
        result_mar.all.return_value = mar_pairs or []
        side_effects.append(result_mar)

    db.execute.side_effect = side_effects
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
