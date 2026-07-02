"""
Rejected Claims service — Step 4 (read) for the Rejected queue.

Fetches the full detail needed by the Rejected Claim Detail screen:
  - claim + claim_fields (SF/BF panels)
  - claim_rejections row (CARC/RARC, triage, resolution state)
  - progress note fields from documented_care_sessions (narrative, activities,
    observations — read by the Appeal Agent)
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.claims import Claim, ClaimFieldsRecord, ClaimRejection
from db.models.pipeline_a import CareRecipient, DocumentedCareSession, StaffShiftAssignment
from schemas.claim import (
    ClaimRead,
    ProgressNoteFields,
    RejectedClaimRead,
    RejectionDetail,
)
from services.clerk_review_service import _make_claim_read, _record_to_claim_fields


async def get_rejected_claim(claim_id: uuid.UUID, db: AsyncSession) -> RejectedClaimRead:
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise KeyError(f"Claim {claim_id} not found")
    if claim.claim_status != "rejected":
        raise KeyError(f"Claim {claim_id} is not a rejected claim")

    rejection = (
        await db.execute(
            select(ClaimRejection).where(ClaimRejection.claim_id == claim_id)
        )
    ).scalar_one_or_none()
    if rejection is None:
        raise KeyError(f"No rejection record found for claim {claim_id}")

    record = await db.get(ClaimFieldsRecord, claim_id)
    billing_fields = _record_to_claim_fields(record).model_dump() if record else None

    # Progress note — join through StaffShiftAssignment to DocumentedCareSession
    note_stmt = (
        select(DocumentedCareSession)
        .join(
            StaffShiftAssignment,
            DocumentedCareSession.shift_assignment_id == StaffShiftAssignment.shift_assignment_id,
        )
        .where(DocumentedCareSession.care_session_id == claim.service_event_id)
    )
    session = (await db.execute(note_stmt)).scalar_one_or_none()
    progress_note: ProgressNoteFields | None = None
    if session is not None:
        progress_note = ProgressNoteFields(
            care_session_narrative=session.care_session_narrative,
            activities_performed=session.activities_performed,
            level_of_support_provided=session.level_of_support_provided,
            health_observations_notes=session.health_observations_notes,
            behavioral_observations_notes=session.behavioral_observations_notes,
        )

    return RejectedClaimRead(
        claim=_make_claim_read(claim),
        billing_fields=billing_fields,
        rejection=RejectionDetail(
            rejection_id=rejection.rejection_id,
            carc_code=rejection.carc_code,
            carc_description=rejection.carc_description,
            rarc_code=rejection.rarc_code,
            rarc_description=rejection.rarc_description,
            payer_rejection_date=rejection.payer_rejection_date,
            raw_ra_reference=rejection.raw_ra_reference,
            triage_category=rejection.triage_category,
            triage_agent_output=rejection.triage_agent_output,
            resolution_action=rejection.resolution_action,
            resolution_status=rejection.resolution_status,
            resubmitted_claim_id=rejection.resubmitted_claim_id,
            appeal_packet_text=rejection.appeal_packet_text,
            resolved_by=rejection.resolved_by,
            resolved_at=rejection.resolved_at,
        ),
        progress_note=progress_note,
    )
