"""
Tests for the Step 4 clerk review route.

These verify the backend contract for clerk review GET and POST.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_db, get_http_client, get_settings
from main import app
from tests.services.conftest import make_db_mock, make_http_mock
from schemas.claim import BillingFieldOverrides, ClaimRead, ClerkReviewConfirmRequest, ClerkReviewRead

_CLAIM_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_EVENT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_NOW = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)


class _MockSettings:
    mock_auth_api_url = "http://mock-auth-api"
    auth_api_timeout = 10.0
    billing_npi = "1234567890"
    tax_id = "12-3456789"
    payer_id = "MOHLTH"
    t2016_fee_schedule_rate = Decimal("487.68")


def _make_claim_fields_record() -> MagicMock:
    record = MagicMock()
    record.claim_id = _CLAIM_ID
    record.subscriber_last_name = "Smith"
    record.subscriber_first_name = "John"
    record.subscriber_medicaid_id = "MO100001"
    record.subscriber_dob = "19820314"
    record.subscriber_sex = "M"
    record.service_date = "20260610"
    record.service_begin_time = None
    record.service_end_time = None
    record.diagnosis_code = "F70"
    record.waiver_type = "Comprehensive"
    record.diagnosis_qualifier = "ABK"
    record.place_of_service = "12"
    record.claim_filing_indicator = "MC"
    record.rendering_npi = "1234567890"
    record.procedure_code = "T2016"
    record.procedure_qualifier = "HC"
    record.modifier_1 = "U1"
    record.modifier_2 = None
    record.modifier_3 = None
    record.service_units = 32
    record.billed_amount = "15606.00"
    record.taxonomy_code = "251G00000X"
    record.notes = None
    return record


def _make_claim() -> MagicMock:
    claim = MagicMock()
    claim.claim_id = _CLAIM_ID
    claim.service_event_id = _EVENT_ID
    claim.patient_auth_number = "AUTH-2026-00101"
    claim.billing_npi = "1234567890"
    claim.payer_id = "MOHLTH"
    claim.billed_amount = Decimal("15606.00")
    claim.claim_status = "draft"
    claim.file_837p_reference = None
    claim.clerk_reviewed_by = None
    claim.clerk_review_timestamp = None
    claim.created_at = _NOW
    return claim


def _make_db_mock_with_claim(claim_id: uuid.UUID) -> AsyncMock:
    db = AsyncMock()
    claim = _make_claim()
    record = _make_claim_fields_record()

    async def _get(model, key):
        if key == claim_id:
            return claim if model.__name__ == "Claim" else record
        return None

    db.get.side_effect = _get
    db.commit = AsyncMock()
    return db


@contextmanager
def _override_deps(db_mock):
    async def _get_db():
        yield db_mock

    def _get_http():
        return make_http_mock()

    def _get_settings():
        return _MockSettings()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_http_client] = _get_http
    app.dependency_overrides[get_settings] = _get_settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_clerk_review_get_returns_draft_claim_and_billing_fields():
    db_mock = _make_db_mock_with_claim(_CLAIM_ID)
    with _override_deps(db_mock) as client:
        response = client.get(f"/api/v1/clerk-review/{_CLAIM_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["claim"]["claim_id"] == str(_CLAIM_ID)
    assert data["billing_fields"]["waiver_type"] == "Comprehensive"


def test_clerk_review_confirm_updates_claim_and_returns_final_read():
    db_mock = _make_db_mock_with_claim(_CLAIM_ID)
    with _override_deps(db_mock) as client:
        request = {
            "clerk_id": "clerk-123",
            "billing_field_overrides": {
                "modifier_1": "U2",
                "billed_amount": "15000.00",
            },
        }
        response = client.post(f"/api/v1/clerk-review/{_CLAIM_ID}/confirm", json=request)

    assert response.status_code == 200
    data = response.json()
    assert data["claim_status"] == "confirmed"
    assert data["clerk_reviewed_by"] == "clerk-123"
    assert data["billed_amount"] == "15000.00"


def test_clerk_review_confirm_generates_final_edi_with_waiver_type_and_tax_id():
    db_mock = _make_db_mock_with_claim(_CLAIM_ID)
    with _override_deps(db_mock) as client:
        request = {
            "clerk_id": "clerk-456",
            "billing_field_overrides": None,
        }
        response = client.post(f"/api/v1/clerk-review/{_CLAIM_ID}/confirm", json=request)

    assert response.status_code == 200
    data = response.json()
    assert data["claim_status"] == "confirmed"
    assert data["clerk_reviewed_by"] == "clerk-456"
    assert data["file_837p_reference"] is not None
    assert "REF*EI" in data["file_837p_reference"]
    assert "123456789" in data["file_837p_reference"]
    assert "NTE*ADD*WaiverType:Comprehensive" in data["file_837p_reference"]
