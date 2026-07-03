"""
Pipeline service — Step 6/7 orchestration entry point.

run_pipeline_for_claim() pre-fetches all claim context, hands it to the
Rejection Pipeline Orchestrator, persists the result, and returns PipelineOutput
for the clerk to review and act on.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.claim_builder.billing_rules import (
    BILLING_PROVIDER_TAXONOMY,
    CLAIM_FILING_INDICATOR,
    DIAGNOSIS_CODE_QUALIFIER,
    PLACE_OF_SERVICE_CODE,
    PROCEDURE_CODE,
    PROCEDURE_CODE_QUALIFIER,
    VALID_MODIFIERS,
)
from agents.rejection_orchestrator.agent import PipelineOutput, run_pipeline
from core.config import settings
from core.exceptions import ClaimBuildError
from db.models.claims import Claim, ClaimFieldsRecord, ClaimRejection
from db.models.pipeline_a import DocumentedCareSession, StaffShiftAssignment
from schemas.claim import PipelineOutput as PipelineOutputSchema


async def run_pipeline_for_claim(
    claim_id: uuid.UUID,
    db: AsyncSession,
) -> PipelineOutputSchema:
    # ── 1. Fetch claim ────────────────────────────────────────────────────────
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")
    if claim.claim_status != "rejected":
        raise KeyError(f"Claim {claim_id} is not a rejected claim")

    # ── 2. Fetch rejection record ─────────────────────────────────────────────
    rejection = (
        await db.execute(
            select(ClaimRejection).where(ClaimRejection.claim_id == claim_id)
        )
    ).scalar_one_or_none()
    if rejection is None:
        raise KeyError(f"No rejection record found for claim {claim_id}")

    # ── 3. Fetch claim fields ─────────────────────────────────────────────────
    record = await db.get(ClaimFieldsRecord, claim_id)
    claim_fields = (
        {c.key: getattr(record, c.key) for c in record.__table__.columns if c.key != "claim_id"}
        if record
        else {}
    )

    # ── 4. Fetch claim history (prior submissions for same service event) ─────
    history_rows = (
        await db.execute(
            select(Claim.claim_id, Claim.claim_status, Claim.created_at)
            .where(
                Claim.service_event_id == claim.service_event_id,
                Claim.claim_id != claim_id,
            )
            .order_by(Claim.created_at.desc())
        )
    ).all()
    claim_history = [
        {
            "claim_id": str(r.claim_id),
            "claim_status": r.claim_status,
            "created_at": str(r.created_at),
        }
        for r in history_rows
    ]

    # ── 5. Fetch progress note ────────────────────────────────────────────────
    note_stmt = (
        select(DocumentedCareSession)
        .join(
            StaffShiftAssignment,
            DocumentedCareSession.shift_assignment_id == StaffShiftAssignment.shift_assignment_id,
        )
        .where(DocumentedCareSession.care_session_id == claim.service_event_id)
    )
    care_session = (await db.execute(note_stmt)).scalar_one_or_none()
    progress_note: dict = {}
    if care_session is not None:
        progress_note = {
            "care_session_narrative": care_session.care_session_narrative,
            "activities_performed": care_session.activities_performed,
            "level_of_support_provided": care_session.level_of_support_provided,
            "health_observations_notes": care_session.health_observations_notes,
            "behavioral_observations_notes": care_session.behavioral_observations_notes,
        }

    # ── 6. Build billing rules payload ────────────────────────────────────────
    billing_rules = {
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
        "raw_ra_reference": rejection.raw_ra_reference,
    }

    # ── 7. Run orchestrator ───────────────────────────────────────────────────
    context = {
        "rejection": rejection_payload,
        "claim_fields": {**claim_fields, "patient_auth_number": claim.patient_auth_number},
        "billing_rules": billing_rules,
        "claim_history": claim_history,
        "progress_note": progress_note,
    }

    result: PipelineOutput = await run_pipeline(context)

    # Safety: if the LLM nested the entire appeal output as the appeal_draft value, unwrap it
    if isinstance(result.appeal_draft, dict):
        result.appeal_draft = result.appeal_draft.get("appeal_draft") or str(result.appeal_draft)

    # Fill in letter placeholders
    if result.appeal_draft:
        today_str = date.today().strftime("%B %d, %Y")
        result.appeal_draft = result.appeal_draft.replace("[Current Date]", today_str)
        result.appeal_draft = result.appeal_draft.replace("[Billing Supervisor Name]", "Sarah Johnson")

    # ── 8. Persist orchestrator output ────────────────────────────────────────
    rejection.triage_category = result.triage_category
    rejection.triage_agent_output = result.model_dump()
    await db.commit()

    # ── 9. Return as API schema ───────────────────────────────────────────────
    return PipelineOutputSchema(
        triage_category=result.triage_category,
        triage_confidence=result.triage_confidence,
        triage_reasoning=result.triage_reasoning,
        triage_recommended_action=result.triage_recommended_action,
        proposed_fields=result.proposed_fields,
        correction_reasoning=result.correction_reasoning,
        correction_confidence=result.correction_confidence,
        appeal_draft=result.appeal_draft,
        appeal_confidence=result.appeal_confidence,
        appeal_key_evidence=result.appeal_key_evidence,
    )
