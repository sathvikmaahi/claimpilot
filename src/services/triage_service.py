"""
Triage service — runs the Triage Agent on a rejected claim and persists the result.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.triage.agent import TriageOutput, run_triage
from core.exceptions import ClaimBuildError
from db.models.claims import Claim, ClaimFieldsRecord, ClaimRejection
from schemas.claim import TriageResponse


async def triage_claim(claim_id: uuid.UUID, db: AsyncSession) -> TriageResponse:
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
    claim_fields = (
        {c.key: getattr(record, c.key) for c in record.__table__.columns if c.key != "claim_id"}
        if record else {}
    )

    # Prior submissions for the same service event (duplicate/history check)
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
        {"claim_id": str(r.claim_id), "claim_status": r.claim_status, "created_at": str(r.created_at)}
        for r in history_rows
    ]

    rejection_payload = {
        "carc_code": rejection.carc_code,
        "carc_description": rejection.carc_description,
        "rarc_code": rejection.rarc_code,
        "rarc_description": rejection.rarc_description,
        "payer_rejection_date": str(rejection.payer_rejection_date),
        "raw_ra_reference": rejection.raw_ra_reference,
    }

    result: TriageOutput = await run_triage(
        rejection=rejection_payload,
        claim_fields=claim_fields,
        claim_history=claim_history,
    )

    # Persist triage result
    rejection.triage_category = result.triage_category
    rejection.triage_agent_output = {
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "recommended_action": result.recommended_action,
    }
    await db.commit()

    return TriageResponse(
        triage_category=result.triage_category,
        confidence=result.confidence,
        reasoning=result.reasoning,
        recommended_action=result.recommended_action,
    )
