"""
Tests for background/revalidation_job.py

Each test mocks the DB session and service functions so no real DB or HTTP
calls are made. Tests cover:
  - Passing claim promoted to 'validated'
  - Still failing claim stays in queue with updated reason
  - Claim not found in DB (db.get returns None) — skipped with warning
  - Fetch error (ServiceEventNotFoundError) — skipped with warning
  - Empty queue — job runs cleanly with nothing to process
  - ValidationFailedError raised with empty list — ValueError at source
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from background.revalidation_job import run_revalidation_job
from core.exceptions import ValidationFailedError, ValidationFailure


def make_mock_claim(claim_id=None):
    """Builds a mock Claim object with a failed status."""
    claim = MagicMock()
    claim.claim_id = claim_id or uuid.uuid4()
    claim.service_event_id = uuid.uuid4()
    claim.patient_auth_number = "AUTH-2026-00101"
    claim.claim_status = "failed"
    claim.validation_failure_check = 1
    claim.validation_failure_reason = "some reason"
    return claim


def make_session_factory(claim_ids: list, db_claim):
    """
    Builds a mock async_session_factory.
    First session call → execute returns claim_ids.
    Subsequent session calls → get returns db_claim.
    """
    session = AsyncMock()

    id_result = MagicMock()
    id_result.scalars.return_value.all.return_value = claim_ids
    session.execute.return_value = id_result
    session.get.return_value = db_claim

    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None

    factory = MagicMock(return_value=cm)
    return factory, session


# --- Pass scenario ---

async def test_passing_claim_promoted_to_validated():
    """
    Input: One failed claim that now passes all 5 checks.
    Description: revalidation job should set claim_status to 'validated'
                 and clear failure fields.
    Output: db_claim.claim_status == 'validated', failure fields set to None.
    """
    claim_id = uuid.uuid4()
    db_claim = make_mock_claim(claim_id)
    factory, session = make_session_factory([claim_id], db_claim)

    mock_event = MagicMock()

    with patch("background.revalidation_job.async_session_factory", factory), \
         patch("background.revalidation_job.fetch_service_event", AsyncMock(return_value=mock_event)), \
         patch("background.revalidation_job.validate_service_event", AsyncMock(return_value=mock_event)):
        await run_revalidation_job()

    assert db_claim.claim_status == "validated"
    assert db_claim.validation_failure_check is None
    assert db_claim.validation_failure_reason is None
    session.commit.assert_called()


# --- Still failing scenario ---

async def test_still_failing_claim_stays_with_updated_reason():
    """
    Input: One failed claim that still fails Check 2 on revalidation.
    Description: revalidation job should update the failure check and reason
                 but leave claim_status as 'failed'.
    Output: db_claim.validation_failure_check == 2, reason updated.
    """
    claim_id = uuid.uuid4()
    db_claim = make_mock_claim(claim_id)
    factory, session = make_session_factory([claim_id], db_claim)

    mock_event = MagicMock()
    failure = ValidationFailure(check=2, reason="Service code mismatch — delivered T2016, authorized for T2021")

    with patch("background.revalidation_job.async_session_factory", factory), \
         patch("background.revalidation_job.fetch_service_event", AsyncMock(return_value=mock_event)), \
         patch("background.revalidation_job.validate_service_event", AsyncMock(side_effect=ValidationFailedError([failure]))):
        await run_revalidation_job()

    assert db_claim.validation_failure_check == 2
    assert "T2021" in db_claim.validation_failure_reason
    session.commit.assert_called()


# --- Claim not found in DB ---

async def test_claim_not_found_in_db_skipped():
    """
    Input: claim_id exists in ID list but db.get returns None.
    Description: Should log a warning and skip — no crash, no commit.
    Output: session.commit not called.
    """
    claim_id = uuid.uuid4()
    factory, session = make_session_factory([claim_id], db_claim=None)

    with patch("background.revalidation_job.async_session_factory", factory), \
         patch("background.revalidation_job.fetch_service_event", AsyncMock()) as mock_fetch:
        await run_revalidation_job()

    mock_fetch.assert_not_called()
    session.commit.assert_not_called()


# --- Fetch error scenario ---

async def test_fetch_error_skipped():
    """
    Input: fetch_service_event raises ServiceEventNotFoundError.
    Description: Should log a warning and skip — claim stays in queue untouched.
    Output: session.commit not called.
    """
    from core.exceptions import ServiceEventNotFoundError

    claim_id = uuid.uuid4()
    db_claim = make_mock_claim(claim_id)
    factory, session = make_session_factory([claim_id], db_claim)

    with patch("background.revalidation_job.async_session_factory", factory), \
         patch("background.revalidation_job.fetch_service_event", AsyncMock(side_effect=ServiceEventNotFoundError("not found"))), \
         patch("background.revalidation_job.validate_service_event", AsyncMock()):
        await run_revalidation_job()

    session.commit.assert_not_called()


# --- Empty queue ---

async def test_empty_queue_completes_cleanly():
    """
    Input: No failed claims in the DB.
    Description: Job should run and exit cleanly with nothing to process.
    Output: No DB writes, no errors.
    """
    factory, session = make_session_factory(claim_ids=[], db_claim=None)

    with patch("background.revalidation_job.async_session_factory", factory), \
         patch("background.revalidation_job.fetch_service_event", AsyncMock()) as mock_fetch:
        await run_revalidation_job()

    mock_fetch.assert_not_called()
    session.commit.assert_not_called()


# --- ValidationFailedError empty list guard ---

def test_validation_failed_error_rejects_empty_failures():
    """
    Input: ValidationFailedError([]) — empty list.
    Description: __init__ should raise ValueError immediately rather than
                 allowing exc.failures[0] to crash later with IndexError.
    Output: ValueError raised.
    """
    with pytest.raises(ValueError, match="at least one failure"):
        ValidationFailedError([])
