"""
Background re-validation job.

Input: None — runs daily against all claims with claim_status='failed'.
Description: Re-checks failed claims to see if blocking conditions have changed.

             Why daily:
             — EVV corrections are resent through the EVV vendor and appear in EAS
               within 24 hours (MO HealthNet EVV daily update cycle).
             — Missing field fixes (NPI, DSP signature) are resolved by billing staff
               same day or next morning.
             — Auth renewals take ~7 days (Missouri Medicaid standard decision time),
               so daily checks catch the renewal as soon as it comes through.

             For each failed claim, re-fetches the EnrichedServiceEvent and re-runs
             all 5 validation checks.
             NOW PASSING → claim_status set to 'validated', failure fields cleared,
                           claim is ready for Step 3 Claim Builder.
             STILL FAILING → failure check and reason updated in case the error changed,
                             claim remains in review queue.

Output: None — updates claim_status rows in claims table as a side effect.
        Logs passed/still_failing/errors count per run for observability.

Scheduling: Run as a Cloud Run Job triggered by Cloud Scheduler — cron: 0 6 * * *
            (06:00 UTC daily, after EVV vendor nightly batch uploads complete).
"""
import asyncio

import httpx
from sqlalchemy import select

from core.config import settings
from core.exceptions import AuthAPIUnavailableError, ServiceEventNotFoundError, ValidationFailedError
from core.logging import logger
from db.models.claims import Claim
from db.session import async_session_factory
from services.fetch_service import fetch_service_event
from services.validation_service import validate_service_event


async def run_revalidation_job() -> None:
    """
    Input: None.
    Description: Queries all failed claims, re-runs the 5 validation checks on each.
                 Passing claims are promoted to 'validated'. Failing claims stay in the
                 review queue with an updated failure reason.
    Output: None — mutates claim_status rows in the claims table.
    """
    passed = 0
    still_failing = 0
    errors = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(Claim).where(Claim.claim_status == "failed")
        )
        failed_claims: list[Claim] = list(result.scalars().all())

    logger.info("revalidation_job: found %d failed claims to re-check", len(failed_claims))

    async with httpx.AsyncClient() as http_client:
        for claim in failed_claims:
            async with async_session_factory() as db:
                try:
                    event = await fetch_service_event(
                        service_event_id=claim.service_event_id,
                        db=db,
                        http_client=http_client,
                        auth_api_url=settings.mock_auth_api_url,
                        auth_api_timeout=settings.auth_api_timeout,
                    )
                except (ServiceEventNotFoundError, AuthAPIUnavailableError) as exc:
                    logger.warning(
                        "revalidation_job: could not fetch claim %s — %s",
                        claim.claim_id,
                        exc,
                    )
                    errors += 1
                    continue

                try:
                    await validate_service_event(event)

                    # All 5 checks passed — promote to validated
                    db_claim = await db.get(Claim, claim.claim_id)
                    db_claim.claim_status = "validated"
                    db_claim.validation_failure_check = None
                    db_claim.validation_failure_reason = None
                    await db.commit()

                    logger.info(
                        "revalidation_job: claim %s now PASSING — promoted to validated",
                        claim.claim_id,
                    )
                    passed += 1

                except ValidationFailedError as exc:
                    # Still failing — update reason in case the blocking check changed
                    db_claim = await db.get(Claim, claim.claim_id)
                    db_claim.validation_failure_check = exc.failures[0].check
                    db_claim.validation_failure_reason = " | ".join(f.reason for f in exc.failures)
                    await db.commit()

                    logger.info(
                        "revalidation_job: claim %s still FAILING check %d — %s",
                        claim.claim_id,
                        exc.check,
                        exc.reason,
                    )
                    still_failing += 1

    logger.info(
        "revalidation_job: complete — passed=%d still_failing=%d errors=%d",
        passed,
        still_failing,
        errors,
    )


if __name__ == "__main__":
    asyncio.run(run_revalidation_job())
