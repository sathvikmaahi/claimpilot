import pytest
import httpx
from uuid import uuid4

from core.exceptions import AuthAPIUnavailableError, ServiceEventNotFoundError
from schemas.service_event import EnrichedServiceEvent
from services.fetch_service import fetch_service_event
from tests.services.conftest import make_db_mock, make_http_mock

AUTH_API_URL = "http://mock-auth-api"


async def test_fetch_success(
    service_event_id,
    mock_session,
    mock_shift,
    mock_location,
    mock_recipient,
    mock_mar_pair,
    auth_response_data,
):
    """
    Input: All joined tables populated, auth API returns valid data.
    Description: Happy path — fetch returns a fully populated EnrichedServiceEvent
                 with one MAR record and authorization details from the mock API.
    Output: EnrichedServiceEvent with correct participant_name, procedure_code, and auth number.
    """
    session_row = (mock_session, mock_shift, mock_location, mock_recipient)
    db = make_db_mock(session_row, mar_pairs=[mock_mar_pair])
    http = make_http_mock(auth_response_data)

    result = await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert isinstance(result, EnrichedServiceEvent)
    assert result.participant_name == "John Smith"
    assert result.procedure_code == "T2016"
    assert result.modifier_1 == "U1"
    assert result.rendering_npi == "1234567890"
    assert result.sex == "M"
    assert result.authorization.patient_prior_auth_number == "AUTH-2026-00101"
    assert len(result.mar_records) == 1
    assert result.mar_records[0].med_name == "Metformin"

    http.post.assert_called_once_with(
        f"{AUTH_API_URL}/authorization",
        json={"patient_name": "John Smith", "insurance_number": "MO100001"},
        timeout=10.0,
    )


async def test_fetch_care_session_not_found(service_event_id, auth_response_data):
    """
    Input: Main joined query (documented_care_sessions + shift + recipient) returns None.
    Description: Missing care session should raise ServiceEventNotFoundError immediately,
                 before querying goals or MAR or calling the auth API.
                 (Replaces test_fetch_missing_progress_notes — progress_notes no longer exists;
                 the new single join replaces the old 2-table approach.)
    Output: ServiceEventNotFoundError with service_event_id in the message.
    """
    db = make_db_mock(session_row=None)
    http = make_http_mock(auth_response_data)

    with pytest.raises(ServiceEventNotFoundError) as exc_info:
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert str(service_event_id) in str(exc_info.value)
    http.post.assert_not_called()


async def test_fetch_with_goals_resolution(
    service_event_id,
    mock_session,
    mock_shift,
    mock_location,
    mock_recipient,
    auth_response_data,
):
    """
    Input: Session has goals_addressed_in_session populated with goal UUIDs.
    Description: Fetch service executes a second query against support_plan_goals to resolve
                 UUIDs → goal_description text. EnrichedServiceEvent.goals_supported receives
                 the resolved strings so the Claim Builder agent sees readable text.
                 (Replaces test_fetch_missing_service_metadata — service_metadata no longer
                 exists as a separate table; that scenario is not possible in the new schema.)
    Output: EnrichedServiceEvent with goals_supported populated from the goals query.
    """
    mock_session.goals_addressed_in_session = [uuid4(), uuid4()]  # non-empty triggers goals query
    session_row = (mock_session, mock_shift, mock_location, mock_recipient)

    goal_texts = [
        "Develop independence in morning ADL routine with minimal prompting",
        "Prepare breakfast and simple meals with verbal guidance",
    ]
    db = make_db_mock(session_row, has_goals=True, goal_descriptions=goal_texts, mar_pairs=[])
    http = make_http_mock(auth_response_data)

    result = await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert isinstance(result, EnrichedServiceEvent)
    assert result.goals_supported == goal_texts
    assert result.mar_records == []


async def test_fetch_empty_mar(
    service_event_id,
    mock_session,
    mock_shift,
    mock_location,
    mock_recipient,
    auth_response_data,
):
    """
    Input: All DB tables present, MAR query returns empty list.
    Description: An empty MAR is valid — not all ISL shifts involve medications.
                 Should return EnrichedServiceEvent with mar_records=[].
    Output: EnrichedServiceEvent with empty mar_records list.
    """
    session_row = (mock_session, mock_shift, mock_location, mock_recipient)
    db = make_db_mock(session_row, mar_pairs=[])
    http = make_http_mock(auth_response_data)

    result = await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert isinstance(result, EnrichedServiceEvent)
    assert result.mar_records == []
    assert result.participant_name == "John Smith"


async def test_fetch_auth_api_unreachable(
    service_event_id,
    mock_session,
    mock_shift,
    mock_location,
    mock_recipient,
    mock_mar_pair,
):
    """
    Input: All DB tables present, auth API raises httpx.ConnectError.
    Description: An unreachable auth API should raise AuthAPIUnavailableError (502).
                 The original ConnectError is chained as the cause.
    Output: AuthAPIUnavailableError with the auth API URL in the message.
    """
    session_row = (mock_session, mock_shift, mock_location, mock_recipient)
    db = make_db_mock(session_row, mar_pairs=[mock_mar_pair])
    http = make_http_mock(raise_exc=httpx.ConnectError("Connection refused"))

    with pytest.raises(AuthAPIUnavailableError) as exc_info:
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert AUTH_API_URL in str(exc_info.value)


async def test_fetch_auth_api_timeout(
    service_event_id,
    mock_session,
    mock_shift,
    mock_location,
    mock_recipient,
    mock_mar_pair,
):
    """
    Input: All DB tables present, auth API raises httpx.TimeoutException.
    Description: A timed-out auth API request should also raise AuthAPIUnavailableError.
    Output: AuthAPIUnavailableError.
    """
    session_row = (mock_session, mock_shift, mock_location, mock_recipient)
    db = make_db_mock(session_row, mar_pairs=[mock_mar_pair])
    http = make_http_mock(raise_exc=httpx.TimeoutException("Request timed out"))

    with pytest.raises(AuthAPIUnavailableError):
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)
