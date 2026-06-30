"""
Process Claims service.

Input: db, http_client, settings.
Description: Finds all documented_care_sessions with no claims row and runs
             Fetch → Validate → Claim Builder for each in sequence.
             PASS → draft claim + ClaimFieldsRecord written to DB.
             FAIL → failed claim written to DB.
Output: ProcessClaimsResult { processed, draft, failed }
"""
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.claim_builder.agent import ClaimFields, run_claim_builder
from core.config import Settings
from core.exceptions import (
    AuthAPIUnavailableError,
    ClaimBuildError,
    DatabaseUnavailableError,
    ServiceEventNotFoundError,
    ValidationFailedError,
)
from db.models.claims import Claim, ClaimFieldsRecord
from db.models.pipeline_a import DocumentedCareSession
from schemas.claim import ProcessClaimsResult
from services.edi_generator import generate_837p
from services.fetch_service import fetch_service_event
from services.validation_service import compute_validation_results, validate_service_event


async def process_all_claims(
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> ProcessClaimsResult:
    stmt = (
        select(DocumentedCareSession.care_session_id)
        .outerjoin(Claim, Claim.service_event_id == DocumentedCareSession.care_session_id)
        .where(Claim.claim_id == None)
    )
    unprocessed = (await db.execute(stmt)).scalars().all()

    draft_count = 0
    failed_count = 0

    for session_id in unprocessed:
        try:
            event = await fetch_service_event(
                service_event_id=session_id,
                db=db,
                http_client=http_client,
                auth_api_url=settings.mock_auth_api_url,
                auth_api_timeout=settings.auth_api_timeout,
            )
        except (ServiceEventNotFoundError, AuthAPIUnavailableError, DatabaseUnavailableError, httpx.HTTPStatusError, Exception):
            failed_count += 1
            continue

        validation_results = compute_validation_results(event)

        try:
            await validate_service_event(event)
        except ValidationFailedError as exc:
            failed_claim = Claim(
                service_event_id=event.service_event_id,
                patient_auth_number=event.authorization.patient_prior_auth_number,
                claim_status="failed",
                validation_failure_check=exc.failures[0].check,
                validation_failure_reason=" | ".join(f.reason for f in exc.failures),
                validation_results=validation_results,
            )
            db.add(failed_claim)
            await db.commit()
            failed_count += 1
            continue

        claim = Claim(
            service_event_id=event.service_event_id,
            patient_auth_number=event.authorization.patient_prior_auth_number,
            billing_npi=settings.billing_npi,
            payer_id=settings.payer_id,
            claim_status="draft",
            validation_results=validation_results,
        )
        db.add(claim)
        await db.flush()

        try:
            fields: ClaimFields = await run_claim_builder(
                event=event,
                fee_rate=settings.t2016_fee_schedule_rate,
            )
        except ClaimBuildError:
            claim.claim_status = "draft_failed"
            await db.commit()
            failed_count += 1
            continue

        edi_text = generate_837p(
            fields=fields,
            billing_npi=settings.billing_npi,
            tax_id=settings.tax_id,
            payer_id=settings.payer_id,
            claim_id=claim.claim_id,
        )
        claim_fields_record = ClaimFieldsRecord(
            claim_id=claim.claim_id,
            subscriber_last_name=fields.subscriber_last_name,
            subscriber_first_name=fields.subscriber_first_name,
            subscriber_medicaid_id=fields.subscriber_medicaid_id,
            subscriber_dob=fields.subscriber_dob,
            subscriber_sex=fields.subscriber_sex,
            service_date=fields.service_date,
            service_begin_time=fields.service_begin_time,
            service_end_time=fields.service_end_time,
            diagnosis_code=fields.diagnosis_code,
            diagnosis_qualifier=fields.diagnosis_qualifier,
            place_of_service=fields.place_of_service,
            claim_filing_indicator=fields.claim_filing_indicator,
            rendering_npi=fields.rendering_npi,
            procedure_code=fields.procedure_code,
            procedure_qualifier=fields.procedure_qualifier,
            modifier_1=fields.modifier_1,
            modifier_2=fields.modifier_2,
            modifier_3=fields.modifier_3,
            service_units=fields.service_units,
            waiver_type=fields.waiver_type,
            billed_amount=fields.billed_amount,
            taxonomy_code=fields.taxonomy_code,
            notes=fields.notes,
        )
        db.add(claim_fields_record)
        claim.billed_amount = Decimal(fields.billed_amount)
        claim.file_837p_reference = edi_text
        claim.claim_status = "draft"
        await db.commit()
        draft_count += 1

    return ProcessClaimsResult(
        processed=len(unprocessed),
        draft=draft_count,
        failed=failed_count,
    )
