"""
Correction service — Step 6 (Correction Agent) for correctable rejected claims.

propose_correction()  — runs the Correction Agent and returns proposed field changes.
resubmit_claim()      — applies clerk-approved overrides, creates a new confirmed claim,
                        and links it back to the original rejection record.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from agents.claim_builder.billing_rules import (
    CLAIM_FILING_INDICATOR,
    DIAGNOSIS_CODE_QUALIFIER,
    PLACE_OF_SERVICE_CODE,
    PROCEDURE_CODE,
    PROCEDURE_CODE_QUALIFIER,
    BILLING_PROVIDER_TAXONOMY,
    VALID_MODIFIERS,
)
from agents.correction.agent import CorrectionOutput, run_correction
from core.config import settings
from core.exceptions import ClaimBuildError
from db.models.claims import Claim, ClaimFieldsRecord, ClaimRejection
from schemas.claim import CorrectionResponse, ResubmitRequest, ResubmitResponse
from services.clerk_review_service import _record_to_claim_fields
from services.edi_generator import generate_837p
from services.edi_validator import validate_837p


async def propose_correction(claim_id: uuid.UUID, db: AsyncSession) -> CorrectionResponse:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")
    if claim.claim_status != "rejected":
        raise KeyError(f"Claim {claim_id} is not a rejected claim")

    from sqlalchemy import select
    rejection = (
        await db.execute(
            select(ClaimRejection).where(ClaimRejection.claim_id == claim_id)
        )
    ).scalar_one_or_none()
    if rejection is None:
        raise KeyError(f"No rejection record found for claim {claim_id}")

    if rejection.triage_category != "correctable":
        raise ClaimBuildError(
            f"Claim {claim_id} is triaged as '{rejection.triage_category}', not 'correctable'."
        )

    record = await db.get(ClaimFieldsRecord, claim_id)
    claim_fields = (
        {c.key: getattr(record, c.key) for c in record.__table__.columns if c.key != "claim_id"}
        if record
        else {}
    )

    billing_rules_payload = {
        "PROCEDURE_CODE": PROCEDURE_CODE,
        "PROCEDURE_CODE_QUALIFIER": PROCEDURE_CODE_QUALIFIER,
        "VALID_MODIFIERS": VALID_MODIFIERS,
        "BILLING_PROVIDER_TAXONOMY": BILLING_PROVIDER_TAXONOMY,
        "CLAIM_FILING_INDICATOR": CLAIM_FILING_INDICATOR,
        "PLACE_OF_SERVICE_CODE": PLACE_OF_SERVICE_CODE,
        "DIAGNOSIS_CODE_QUALIFIER": DIAGNOSIS_CODE_QUALIFIER,
        "fee_schedule_rate": str(settings.t2016_fee_schedule_rate),
    }

    rejection_payload = {
        "carc_code": rejection.carc_code,
        "carc_description": rejection.carc_description,
        "rarc_code": rejection.rarc_code,
        "rarc_description": rejection.rarc_description,
        "payer_rejection_date": str(rejection.payer_rejection_date),
    }

    result: CorrectionOutput = await run_correction(
        rejection=rejection_payload,
        claim_fields=claim_fields,
        billing_rules=billing_rules_payload,
    )

    return CorrectionResponse(
        proposed_fields=result.proposed_fields,
        reasoning=result.reasoning,
        confidence=result.confidence,
    )


async def resubmit_claim(
    claim_id: uuid.UUID,
    request: ResubmitRequest,
    db: AsyncSession,
) -> ResubmitResponse:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")
    if claim.claim_status != "rejected":
        raise KeyError(f"Claim {claim_id} is not a rejected claim")

    from sqlalchemy import select
    rejection = (
        await db.execute(
            select(ClaimRejection).where(ClaimRejection.claim_id == claim_id)
        )
    ).scalar_one_or_none()
    if rejection is None:
        raise KeyError(f"No rejection record found for claim {claim_id}")

    if rejection.triage_category != "correctable":
        raise ClaimBuildError(
            f"Claim {claim_id} is triaged as '{rejection.triage_category}', not 'correctable'."
        )

    # Build corrected fields from original record + approved overrides
    record = await db.get(ClaimFieldsRecord, claim_id)
    if record is None:
        raise KeyError(f"Claim fields for {claim_id} not found")

    fields = _record_to_claim_fields(record)
    fields_dict = fields.model_dump()
    if request.approved_fields:
        for field_name, value in request.approved_fields.items():
            if field_name in fields_dict:
                fields_dict[field_name] = value

    from agents.claim_builder.agent import ClaimFields
    corrected_fields = ClaimFields(**fields_dict)

    # Validate EDI structure before creating the new claim
    edi_text = generate_837p(
        fields=corrected_fields,
        billing_npi=claim.billing_npi or "",
        tax_id=settings.tax_id,
        payer_id=claim.payer_id or "",
        claim_id=uuid.uuid4(),  # placeholder — will be replaced after insert
    )
    edi_errors = validate_837p(edi_text)
    if edi_errors:
        raise ClaimBuildError(f"Resubmitted EDI failed structural check: {'; '.join(edi_errors)}")

    # Create new Claim row (status = confirmed, same service_event_id)
    new_claim_id = uuid.uuid4()
    new_claim = Claim(
        claim_id=new_claim_id,
        service_event_id=claim.service_event_id,
        patient_auth_number=claim.patient_auth_number,
        billing_npi=claim.billing_npi,
        payer_id=claim.payer_id,
        billed_amount=Decimal(corrected_fields.billed_amount),
        claim_status="confirmed",
        clerk_reviewed_by=request.clerk_id,
        clerk_review_timestamp=datetime.now(timezone.utc),
    )

    # Generate final EDI with the real new claim_id
    final_edi = generate_837p(
        fields=corrected_fields,
        billing_npi=claim.billing_npi or "",
        tax_id=settings.tax_id,
        payer_id=claim.payer_id or "",
        claim_id=new_claim_id,
    )
    new_claim.file_837p_reference = final_edi

    db.add(new_claim)
    await db.flush()  # so new_claim_id is committed to the session

    # Create corresponding ClaimFieldsRecord for new claim
    # Use corrected_fields.model_dump() so Pydantic-coerced types (e.g. service_units as int) are used
    coerced = corrected_fields.model_dump()
    new_record = ClaimFieldsRecord(
        claim_id=new_claim_id,
        **{
            k: v
            for k, v in coerced.items()
            if k not in ("notes",)
        },
        notes=coerced.get("notes"),
    )
    db.add(new_record)

    # Mark original claim as resubmitted so it leaves the rejected queue
    claim.claim_status = "resubmitted"

    # Link rejection → new claim
    rejection.resubmitted_claim_id = new_claim_id
    rejection.resolution_status = "in_progress"
    rejection.resolution_action = "resubmit"

    await db.commit()

    return ResubmitResponse(
        new_claim_id=new_claim_id,
        claim_status="confirmed",
        edi_snippet=final_edi[:500],
    )
