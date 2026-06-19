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
    file_837p_reference: str | None
    clerk_reviewed_by: str | None
    clerk_review_timestamp: datetime | None
    created_at: datetime
