"""
Stub — schemas for Pipeline B claim records.

Input: Validated EnrichedServiceEvent + Life Unlimited billing config.
Description: Pydantic schemas representing the claims table and the 837P EDI output.
             ClaimCreate is used when Pipeline B writes a new claim row.
             ClaimRead is returned to the billing clerk on the review screen.
             ClaimStatus tracks the lifecycle: draft → validated → clerk_reviewed → confirmed.
Output: Used by Step 3 (Claim Builder) and Step 4 (Clerk Review) routes and services.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ClaimCreate(BaseModel):
    service_event_id: uuid.UUID
    patient_auth_number: str
    billing_npi: str
    payer_id: str
    billed_amount: Decimal
    claim_status: str = "draft"


class ClaimRead(BaseModel):
    claim_id: uuid.UUID
    service_event_id: uuid.UUID
    patient_auth_number: str
    billing_npi: str
    payer_id: str
    billed_amount: Decimal
    claim_status: str
    validation_results: list[dict] | None = None
    file_837p_reference: str | None
    clerk_reviewed_by: str | None
    clerk_review_timestamp: datetime | None
    created_at: datetime


class BillingFieldOverrides(BaseModel):
    procedure_code: str | None = None
    modifier_1: str | None = None
    modifier_2: str | None = None
    modifier_3: str | None = None
    service_units: int | None = None
    billed_amount: str | None = None
    rendering_npi: str | None = None
    waiver_type: str | None = None
    diagnosis_code: str | None = None
    billing_npi: str | None = None
    payer_id: str | None = None


class ClerkReviewConfirmRequest(BaseModel):
    clerk_id: str
    billing_field_overrides: BillingFieldOverrides | None = None


class ClerkReviewRead(BaseModel):
    claim: ClaimRead
    billing_fields: dict[str, str | int | None] | None = None


class ClaimQueueCard(BaseModel):
    claim_id: uuid.UUID
    service_event_id: uuid.UUID
    patient_auth_number: str
    claim_status: str
    billed_amount: Decimal | None = None
    validation_failure_check: int | None = None
    validation_failure_reason: str | None = None
    created_at: datetime
    clerk_reviewed_by: str | None = None
    clerk_review_timestamp: datetime | None = None
    subscriber_last_name: str | None = None
    subscriber_first_name: str | None = None
    patient_name: str | None = None


class EdiPreviewRequest(BaseModel):
    billing_field_overrides: BillingFieldOverrides | None = None


class EdiPreviewResponse(BaseModel):
    edi: str


class ClaimQueueResponse(BaseModel):
    validated: list[ClaimQueueCard]
    failed: list[ClaimQueueCard]
    confirmed: list[ClaimQueueCard]


class ProcessClaimsResult(BaseModel):
    processed: int
    draft: int
    failed: int
