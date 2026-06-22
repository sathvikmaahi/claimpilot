import pytest
import httpx

from core.exceptions import AuthAPIUnavailableError, ServiceEventNotFoundError
from schemas.service_event import EnrichedServiceEvent
from services.fetch_service import fetch_service_event
from tests.services.conftest import make_db_mock, make_http_mock

AUTH_API_URL = "http://mock-auth-api"


async def test_fetch_success(
    service_event_id,
    mock_progress_note,
    mock_service_meta,
    mock_mar_record,
    auth_response_data,
):
    """
    Input: All 3 Pipeline A tables populated, auth API returns valid data.
    Description: Happy path — fetch returns a fully populated EnrichedServiceEvent
                 with one MAR record and authorization details from the mock API.
    Output: EnrichedServiceEvent with correct participant_name, procedure_code, and auth number.
    """
    db = make_db_mock(mock_progress_note, mock_service_meta, [mock_mar_record])
    http = make_http_mock(auth_response_data)

    result = await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert isinstance(result, EnrichedServiceEvent)
    assert result.participant_name == "John Smith"
    assert result.procedure_code == "T2016"
    assert result.modifier_1 == "UP"
    assert result.authorization.patient_prior_auth_number == "AUTH-2026-00101"
    assert len(result.mar_records) == 1
    assert result.mar_records[0].med_name == "Metformin"

    http.post.assert_called_once_with(
        f"{AUTH_API_URL}/authorization",
        json={"patient_name": "John Smith", "insurance_number": "MO100001"},
        timeout=10.0,
    )


async def test_fetch_missing_progress_notes(service_event_id, auth_response_data):
    """
    Input: progress_notes query returns None.
    Description: Missing progress_notes record should raise ServiceEventNotFoundError
                 immediately, before querying service_metadata or calling the auth API.
    Output: ServiceEventNotFoundError with service_event_id in the message.
    """
    db = make_db_mock(progress_note=None)
    http = make_http_mock(auth_response_data)

    with pytest.raises(ServiceEventNotFoundError) as exc_info:
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert str(service_event_id) in str(exc_info.value)
    http.post.assert_not_called()


async def test_fetch_missing_service_metadata(
    service_event_id,
    mock_progress_note,
    auth_response_data,
):
    """
    Input: progress_notes present, service_metadata query returns None.
    Description: Missing service_metadata should raise ServiceEventNotFoundError
                 before the auth API is called.
    Output: ServiceEventNotFoundError with service_event_id in the message.
    """
    db = make_db_mock(progress_note=mock_progress_note, service_meta=None)
    http = make_http_mock(auth_response_data)

    with pytest.raises(ServiceEventNotFoundError) as exc_info:
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert str(service_event_id) in str(exc_info.value)
    http.post.assert_not_called()


async def test_fetch_empty_mar(
    service_event_id,
    mock_progress_note,
    mock_service_meta,
    auth_response_data,
):
    """
    Input: All DB tables present, MAR query returns empty list.
    Description: An empty MAR is valid — not all ISL shifts involve medications.
                 Should return EnrichedServiceEvent with mar_records=[].
    Output: EnrichedServiceEvent with empty mar_records list.
    """
    db = make_db_mock(mock_progress_note, mock_service_meta, mar_records=[])
    http = make_http_mock(auth_response_data)

    result = await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert isinstance(result, EnrichedServiceEvent)
    assert result.mar_records == []
    assert result.participant_name == "John Smith"


async def test_fetch_auth_api_unreachable(
    service_event_id,
    mock_progress_note,
    mock_service_meta,
    mock_mar_record,
):
    """
    Input: All DB tables present, auth API raises httpx.ConnectError.
    Description: An unreachable auth API should raise AuthAPIUnavailableError (502).
                 The original ConnectError is chained as the cause.
    Output: AuthAPIUnavailableError with the auth API URL in the message.
    """
    db = make_db_mock(mock_progress_note, mock_service_meta, [mock_mar_record])
    http = make_http_mock(raise_exc=httpx.ConnectError("Connection refused"))

    with pytest.raises(AuthAPIUnavailableError) as exc_info:
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)

    assert AUTH_API_URL in str(exc_info.value)


async def test_fetch_auth_api_timeout(
    service_event_id,
    mock_progress_note,
    mock_service_meta,
    mock_mar_record,
):
    """
    Input: All DB tables present, auth API raises httpx.TimeoutException.
    Description: A timed-out auth API request should also raise AuthAPIUnavailableError.
    Output: AuthAPIUnavailableError.
    """
    db = make_db_mock(mock_progress_note, mock_service_meta, [mock_mar_record])
    http = make_http_mock(raise_exc=httpx.TimeoutException("Request timed out"))

    with pytest.raises(AuthAPIUnavailableError):
        await fetch_service_event(service_event_id, db, http, AUTH_API_URL)
