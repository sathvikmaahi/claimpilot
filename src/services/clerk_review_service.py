"""
Step 4: Clerk Review.

Input: draft ClaimRead from Step 3 + optional billing field corrections from the clerk.
Description: Presents the billing clerk with a two-panel view:
             Service Fields (SF) — read-only fields from Pipeline A (participant, shift times, activities, DSP signature, EVV status).
             Billing Fields (BF) — editable fields built by the Claim Builder (procedure code, modifiers, units, billed amount,
             rendering NPI, billing NPI, waiver type, diagnosis code, payer ID).
             SF is read-only because it is the DSP's legal sign-off from Pipeline A — modifying it would
             constitute falsification of a legal document. BF represents administrative coding decisions
             the clerk owns and can correct before confirming.
             On clerk Confirm, updates claim_status to "confirmed" and records clerk_reviewed_by + clerk_review_timestamp.
Output: Confirmed ClaimRead with claim_status="confirmed". This is the final output of Pipeline B.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from agents.claim_builder.agent import ClaimFields
from services.edi_generator import generate_837p
from core.config import Settings
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.claims import Claim, ClaimFieldsRecord
from schemas.claim import BillingFieldOverrides, ClaimRead, ClerkReviewRead


def _make_claim_read(claim: Claim) -> ClaimRead:
    return ClaimRead(
        claim_id=claim.claim_id,
        service_event_id=claim.service_event_id,
        patient_auth_number=claim.patient_auth_number,
        billing_npi=claim.billing_npi or "",
        payer_id=claim.payer_id or "",
        billed_amount=claim.billed_amount or Decimal("0.00"),
        claim_status=claim.claim_status,
        file_837p_reference=claim.file_837p_reference,
        clerk_reviewed_by=claim.clerk_reviewed_by,
        clerk_review_timestamp=claim.clerk_review_timestamp,
        created_at=claim.created_at,
    )


def _record_to_claim_fields(record: ClaimFieldsRecord) -> ClaimFields:
    return ClaimFields(
        subscriber_last_name=record.subscriber_last_name,
        subscriber_first_name=record.subscriber_first_name,
        subscriber_medicaid_id=record.subscriber_medicaid_id,
        subscriber_dob=record.subscriber_dob,
        subscriber_sex=record.subscriber_sex,
        service_date=record.service_date,
        service_begin_time=record.service_begin_time,
        service_end_time=record.service_end_time,
        diagnosis_code=record.diagnosis_code,
        waiver_type=record.waiver_type,
        diagnosis_qualifier=record.diagnosis_qualifier,
        place_of_service=record.place_of_service,
        claim_filing_indicator=record.claim_filing_indicator,
        rendering_npi=record.rendering_npi,
        procedure_code=record.procedure_code,
        procedure_qualifier=record.procedure_qualifier,
        modifier_1=record.modifier_1,
        modifier_2=record.modifier_2,
        modifier_3=record.modifier_3,
        service_units=record.service_units,
        billed_amount=record.billed_amount,
        taxonomy_code=record.taxonomy_code,
        notes=record.notes,
    )


async def get_clerk_review_data(claim_id: uuid.UUID, db: AsyncSession) -> ClerkReviewRead:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")

    record = await db.get(ClaimFieldsRecord, claim_id)
    if record is None:
        raise KeyError(f"Claim fields for {claim_id} not found")

    return ClerkReviewRead(claim=_make_claim_read(claim), billing_fields=_record_to_claim_fields(record).model_dump())


async def confirm_claim(
    claim_id: uuid.UUID,
    clerk_id: str,
    billing_field_overrides: BillingFieldOverrides | None,
    db: AsyncSession,
    settings: Settings,
) -> ClaimRead:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")

    record = await db.get(ClaimFieldsRecord, claim_id)
    if record is None:
        raise KeyError(f"Claim fields for {claim_id} not found")

    if billing_field_overrides is not None:
        overrides = billing_field_overrides.model_dump(exclude_none=True)
        for field_name, value in overrides.items():
            if field_name in {
                "procedure_code",
                "modifier_1",
                "modifier_2",
                "modifier_3",
                "service_units",
                "billed_amount",
                "rendering_npi",
                "waiver_type",
                "diagnosis_code",
            }:
                setattr(record, field_name, value)
            elif field_name == "billing_npi":
                claim.billing_npi = value
            elif field_name == "payer_id":
                claim.payer_id = value

    updated_fields = _record_to_claim_fields(record)
    claim.billed_amount = Decimal(updated_fields.billed_amount)
    claim.file_837p_reference = generate_837p(
        fields=updated_fields,
        billing_npi=claim.billing_npi or "",
        tax_id=settings.tax_id,
        payer_id=claim.payer_id or "",
        claim_id=claim.claim_id,
    )
    claim.claim_status = "confirmed"
    claim.clerk_reviewed_by = clerk_id
    claim.clerk_review_timestamp = datetime.now(timezone.utc)

    await db.commit()
    return _make_claim_read(claim)
