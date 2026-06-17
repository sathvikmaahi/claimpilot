import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AuthAPIUnavailableError, ServiceEventNotFoundError
from db.models.pipeline_a import MAR, ProgressNote, ServiceMetadata
from schemas.auth import AuthorizationDetails
from schemas.service_event import EnrichedServiceEvent, MARRecord


async def fetch_service_event(
    service_event_id: uuid.UUID,
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    auth_api_url: str,
) -> EnrichedServiceEvent:
    """
    Input: service_event_id (UUID), async DB session, httpx async client, auth API base URL.
    Description: Step 1 (Fetch) — queries all three Pipeline A tables for the given service event,
                 then enriches the result by calling the mock Medicaid authorization API.
                 Empty MAR is valid (not all shifts have medications).
                 progress_notes or service_metadata missing → 404.
                 Auth API unreachable or timed out → 502.
    Output: EnrichedServiceEvent merging all Pipeline A data with the patient authorization details.
    """
    # 1 — progress_notes (required)
    result = await db.execute(
        select(ProgressNote).where(ProgressNote.service_event_id == service_event_id)
    )
    progress_note = result.scalar_one_or_none()
    if progress_note is None:
        raise ServiceEventNotFoundError(
            f"No progress_notes record found for service_event_id={service_event_id}"
        )

    # 2 — service_metadata (required)
    result = await db.execute(
        select(ServiceMetadata).where(ServiceMetadata.service_event_id == service_event_id)
    )
    service_meta = result.scalar_one_or_none()
    if service_meta is None:
        raise ServiceEventNotFoundError(
            f"No service_metadata record found for service_event_id={service_event_id}"
        )

    # 3 — MAR (optional — empty list is valid)
    result = await db.execute(
        select(MAR).where(MAR.service_event_id == service_event_id)
    )
    mar_rows = list(result.scalars().all())

    # 4 — Mock Medicaid authorization API
    try:
        response = await http_client.post(
            f"{auth_api_url}/authorization",
            json={
                "patient_name": progress_note.participant_name,
                "insurance_number": progress_note.participant_dcn,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        auth_data = response.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise AuthAPIUnavailableError(
            f"Mock auth API unreachable at {auth_api_url}: {exc}"
        ) from exc

    return EnrichedServiceEvent(
        # progress_notes fields
        service_event_id=progress_note.service_event_id,
        participant_name=progress_note.participant_name,
        participant_dcn=progress_note.participant_dcn,
        participant_dob=progress_note.participant_dob,
        service_date=progress_note.service_date,
        begin_time=progress_note.begin_time,
        end_time=progress_note.end_time,
        service_location=progress_note.service_location,
        provider_name=progress_note.provider_name,
        provider_signature=progress_note.provider_signature,
        service_description=progress_note.service_description,
        activity_time=progress_note.activity_time,
        participation_level=progress_note.participation_level,
        support_level=progress_note.support_level,
        goals_supported=progress_note.goals_supported,
        activity_category=progress_note.activity_category,
        health_observations=progress_note.health_observations,
        behavioral_notes=progress_note.behavioral_notes,
        community_activity=progress_note.community_activity,
        meal_type=progress_note.meal_type,
        personal_care_type=progress_note.personal_care_type,
        # service_metadata fields
        evv_checkin_lat=service_meta.evv_checkin_lat,
        evv_checkin_lng=service_meta.evv_checkin_lng,
        evv_checkout_lat=service_meta.evv_checkout_lat,
        evv_checkout_lng=service_meta.evv_checkout_lng,
        evv_caregiver_id=service_meta.evv_caregiver_id,
        diagnosis_code=service_meta.diagnosis_code,
        waiver_identifier=service_meta.waiver_identifier,
        duration_minutes=service_meta.duration_minutes,
        service_units=service_meta.service_units,
        rendering_npi=service_meta.rendering_npi,
        procedure_code=service_meta.procedure_code,
        modifier_1=service_meta.modifier_1,
        modifier_2=service_meta.modifier_2,
        modifier_3=service_meta.modifier_3,
        authorization_number=service_meta.authorization_number,
        flags=service_meta.flags,
        overall_confidence=service_meta.overall_confidence,
        # MAR rows
        mar_records=[
            MARRecord(
                id=mar.id,
                service_event_id=mar.service_event_id,
                med_name=mar.med_name,
                med_dosage=mar.med_dosage,
                med_time_administered=mar.med_time_administered,
                variance_code=mar.variance_code,
            )
            for mar in mar_rows
        ],
        # auth API
        authorization=AuthorizationDetails(**auth_data),
    )
