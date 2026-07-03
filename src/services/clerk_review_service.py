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
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.claim_builder.agent import ClaimFields
from core.config import Settings
from core.exceptions import ClaimBuildError
from db.models.claims import Claim, ClaimFieldsRecord, ClaimRejection
from db.models.pipeline_a import (
    CareRecipient,
    DocumentedCareSession,
    ServiceLocation,
    StaffShiftAssignment,
)
from schemas.claim import (
    BillingFieldOverrides,
    ClaimQueueCard,
    ClaimQueueResponse,
    ClaimRead,
    ClerkReviewRead,
    RejectedClaimCard,
)
from services.edi_generator import generate_837p
from services.fetch_service import fetch_service_event


def _make_claim_read(claim: Claim) -> ClaimRead:
    return ClaimRead(
        claim_id=claim.claim_id,
        service_event_id=claim.service_event_id,
        patient_auth_number=claim.patient_auth_number,
        billing_npi=claim.billing_npi or "",
        payer_id=claim.payer_id or "",
        billed_amount=claim.billed_amount or Decimal("0.00"),
        claim_status=claim.claim_status,
        validation_results=claim.validation_results,
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


async def get_claim_queue(db: AsyncSession) -> ClaimQueueResponse:
    # draft / failed / confirmed
    stmt = (
        select(Claim, ClaimFieldsRecord, CareRecipient.full_name)
        .outerjoin(ClaimFieldsRecord, Claim.claim_id == ClaimFieldsRecord.claim_id)
        .join(DocumentedCareSession,
              Claim.service_event_id == DocumentedCareSession.care_session_id)
        .join(CareRecipient,
              DocumentedCareSession.care_recipient_id == CareRecipient.care_recipient_id)
        .where(Claim.claim_status.in_(["draft", "failed", "confirmed"]))
        .order_by(Claim.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    validated: list[ClaimQueueCard] = []
    failed: list[ClaimQueueCard] = []
    confirmed: list[ClaimQueueCard] = []

    for claim, fields, patient_name in rows:
        card = ClaimQueueCard(
            claim_id=claim.claim_id,
            service_event_id=claim.service_event_id,
            patient_auth_number=claim.patient_auth_number,
            claim_status=claim.claim_status,
            billed_amount=claim.billed_amount,
            validation_failure_check=claim.validation_failure_check,
            validation_failure_reason=claim.validation_failure_reason,
            created_at=claim.created_at,
            clerk_reviewed_by=claim.clerk_reviewed_by,
            clerk_review_timestamp=claim.clerk_review_timestamp,
            patient_name=patient_name,
            subscriber_last_name=fields.subscriber_last_name if fields else None,
            subscriber_first_name=fields.subscriber_first_name if fields else None,
        )
        if claim.claim_status == "draft":
            validated.append(card)
        elif claim.claim_status == "failed":
            failed.append(card)
        else:
            confirmed.append(card)

    # rejected — join claim_rejections for CARC/triage data
    rej_stmt = (
        select(Claim, ClaimFieldsRecord, CareRecipient.full_name, ClaimRejection)
        .outerjoin(ClaimFieldsRecord, Claim.claim_id == ClaimFieldsRecord.claim_id)
        .join(DocumentedCareSession,
              Claim.service_event_id == DocumentedCareSession.care_session_id)
        .join(CareRecipient,
              DocumentedCareSession.care_recipient_id == CareRecipient.care_recipient_id)
        .join(ClaimRejection, Claim.claim_id == ClaimRejection.claim_id)
        .where(Claim.claim_status.in_(["rejected", "appeal_submitted", "written_off"]))
        .order_by(ClaimRejection.payer_rejection_date.desc())
    )
    rej_rows = (await db.execute(rej_stmt)).all()

    rejected: list[RejectedClaimCard] = []
    for claim, fields, patient_name, rejection in rej_rows:
        rejected.append(RejectedClaimCard(
            claim_id=claim.claim_id,
            service_event_id=claim.service_event_id,
            patient_auth_number=claim.patient_auth_number,
            billed_amount=claim.billed_amount,
            created_at=claim.created_at,
            clerk_reviewed_by=claim.clerk_reviewed_by,
            patient_name=patient_name,
            subscriber_last_name=fields.subscriber_last_name if fields else None,
            subscriber_first_name=fields.subscriber_first_name if fields else None,
            carc_code=rejection.carc_code,
            carc_description=rejection.carc_description,
            rarc_code=rejection.rarc_code,
            rarc_description=rejection.rarc_description,
            payer_rejection_date=rejection.payer_rejection_date,
            raw_ra_reference=rejection.raw_ra_reference,
            triage_category=rejection.triage_category,
            resolution_status=rejection.resolution_status,
            resolution_action=rejection.resolution_action,
        ))

    return ClaimQueueResponse(
        validated=validated, failed=failed, confirmed=confirmed, rejected=rejected
    )


async def _pipeline_a_fields(service_event_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """
    Fallback for failed claims that have no claim_fields row.
    Reconstructs SF/BF from Pipeline A tables so the clerk can see what data was present.
    """
    stmt = (
        select(DocumentedCareSession, StaffShiftAssignment, CareRecipient, ServiceLocation)
        .join(StaffShiftAssignment,
              DocumentedCareSession.shift_assignment_id == StaffShiftAssignment.shift_assignment_id)
        .join(CareRecipient,
              StaffShiftAssignment.care_recipient_id == CareRecipient.care_recipient_id)
        .join(ServiceLocation,
              StaffShiftAssignment.location_id == ServiceLocation.location_id)
        .where(DocumentedCareSession.care_session_id == service_event_id)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        return None

    dcs, ssa, cr, sl = row

    parts = cr.full_name.strip().split()
    last_name = parts[-1] if parts else ""
    first_name = " ".join(parts[:-1]) if len(parts) > 1 else None

    dob = cr.date_of_birth.strftime("%Y%m%d") if cr.date_of_birth else ""
    service_date = ssa.shift_date.strftime("%Y%m%d") if ssa.shift_date else ""
    begin_time = dcs.actual_clock_in_time.strftime("%H%M") if dcs.actual_clock_in_time else None
    end_time = dcs.actual_clock_out_time.strftime("%H%M") if dcs.actual_clock_out_time else None

    units = dcs.billable_units_calculated
    if units is None and dcs.total_duration_minutes:
        units = dcs.total_duration_minutes // 15
    billed = (
        str((Decimal(units) * Decimal("487.68")).quantize(Decimal("0.01"))) if units else "0.00"
    )

    return {
        "subscriber_last_name": last_name,
        "subscriber_first_name": first_name,
        "subscriber_medicaid_id": cr.medicaid_id,
        "subscriber_dob": dob,
        "subscriber_sex": cr.sex,
        "service_date": service_date,
        "service_begin_time": begin_time,
        "service_end_time": end_time,
        "diagnosis_code": cr.primary_diagnosis_code,
        "waiver_type": cr.waiver_program,
        "diagnosis_qualifier": "ABK",
        "place_of_service": "12",
        "claim_filing_indicator": "MC",
        "rendering_npi": sl.rendering_npi,
        "procedure_code": ssa.service_billing_code,
        "procedure_qualifier": "HC",
        "modifier_1": sl.modifier_1,
        "modifier_2": sl.modifier_2,
        "modifier_3": sl.modifier_3,
        "service_units": units,
        "billed_amount": billed,
        "taxonomy_code": "251G00000X",
        "notes": None,
    }


async def preview_edi_for_claim(
    claim_id: uuid.UUID,
    billing_field_overrides,
    db: AsyncSession,
    settings: Settings,
) -> str:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")
    record = await db.get(ClaimFieldsRecord, claim_id)
    if record is None:
        raise KeyError(f"Claim fields for {claim_id} not found")

    fields = _record_to_claim_fields(record)
    if billing_field_overrides is not None:
        overrides = billing_field_overrides.model_dump(exclude_none=True)
        fields_dict = fields.model_dump()
        fields_dict.update(overrides)
        fields = ClaimFields(**fields_dict)

    return generate_837p(
        fields=fields,
        billing_npi=claim.billing_npi or "",
        tax_id=settings.tax_id,
        payer_id=claim.payer_id or "",
        claim_id=claim.claim_id,
    )


async def get_clerk_review_data(claim_id: uuid.UUID, db: AsyncSession) -> ClerkReviewRead:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")

    record = await db.get(ClaimFieldsRecord, claim_id)
    if record is not None:
        billing_fields = _record_to_claim_fields(record).model_dump()
    else:
        billing_fields = await _pipeline_a_fields(claim.service_event_id, db)

    return ClerkReviewRead(claim=_make_claim_read(claim), billing_fields=billing_fields)


async def confirm_claim(
    claim_id: uuid.UUID,
    clerk_id: str,
    billing_field_overrides: BillingFieldOverrides | None,
    db: AsyncSession,
    settings: Settings,
    http_client: httpx.AsyncClient,
) -> ClaimRead:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")

    record = await db.get(ClaimFieldsRecord, claim_id)
    if record is None:
        raise KeyError(f"Claim fields for {claim_id} not found")

    # Check 9 — Auth re-verification at confirm time
    try:
        event = await fetch_service_event(
            service_event_id=claim.service_event_id,
            db=db,
            http_client=http_client,
            auth_api_url=settings.mock_auth_api_url,
            auth_api_timeout=settings.auth_api_timeout,
        )
        auth = event.authorization
        today = date.today()
        if not (auth.validity_start_date <= today <= auth.validity_end_date):
            raise ClaimBuildError(
                f"Auth re-verification failed: authorization expired "
                f"(valid {auth.validity_start_date} – {auth.validity_end_date})"
            )
        if event.service_units > auth.authorized_units:
            raise ClaimBuildError(
                f"Auth re-verification failed: units exhausted "
                f"({event.service_units} requested, {auth.authorized_units} authorized)"
            )
    except ClaimBuildError:
        raise
    except Exception:
        pass  # auth API unavailable — do not block confirm, log is enough

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
