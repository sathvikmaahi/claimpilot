"""
Step 1: Fetch.

Input: service_event_id (UUID) — maps to documented_care_sessions.care_session_id.
Description: Joins DocumentedCareSession with StaffShiftAssignment and CareRecipient
             to build a flat EnrichedServiceEvent. Resolves ISP goal UUIDs to readable
             text via support_plan_goals. Fetches MAR records joined with
             prescribed_medications. Finally calls the mock Medicaid authorization API.
             Empty MAR is valid (not all shifts involve medications).
             Session not found in joined query → 404.
             Auth API unreachable or timed out → 502.
Output: EnrichedServiceEvent merging all Pipeline A data with patient authorization.
"""
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AuthAPIUnavailableError, DatabaseUnavailableError, ServiceEventNotFoundError
from db.models.pipeline_a import (
    CareRecipient,
    DocumentedCareSession,
    MedicationAdministrationRecord,
    PrescribedMedication,
    ServiceLocation,
    StaffShiftAssignment,
    SupportPlanGoal,
)
from schemas.auth import AuthorizationDetails
from schemas.service_event import EnrichedServiceEvent, MARRecord

# Maps service_billing_code → human-readable category for the agent
_BILLING_CODE_TO_CATEGORY: dict[str, str] = {
    "T2016": "Residential Habilitation",
    "T2021": "Day Habilitation",
    "H2014": "Supported Employment",
    "H0004": "ABA Therapy",
    "H2015": "Skill Development",
    "T2025": "Community Networking",
    "H2023": "Prevocational",
    "T2003": "Transportation",
}


async def fetch_service_event(
    service_event_id: uuid.UUID,
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    auth_api_url: str,
    auth_api_timeout: float = 10.0,
) -> EnrichedServiceEvent:
    """
    Input: service_event_id, async DB session, httpx async client, auth API base URL.
    Description: Step 1 (Fetch) — see module docstring.
    Output: EnrichedServiceEvent merging all Pipeline A data with patient authorization.
    """
    # 1 — Main join: documented_care_sessions + staff_shift_assignments + care_recipients
    try:
        result = await db.execute(
            select(DocumentedCareSession, StaffShiftAssignment, ServiceLocation, CareRecipient)
            .join(
                StaffShiftAssignment,
                DocumentedCareSession.shift_assignment_id == StaffShiftAssignment.shift_assignment_id,
            )
            .join(
                ServiceLocation,
                StaffShiftAssignment.location_id == ServiceLocation.location_id,
            )
            .join(
                CareRecipient,
                DocumentedCareSession.care_recipient_id == CareRecipient.care_recipient_id,
            )
            .where(DocumentedCareSession.care_session_id == service_event_id)
        )
        row = result.one_or_none()
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError(
            f"DB query failed for service_event_id={service_event_id}: {exc}"
        ) from exc

    if row is None:
        raise ServiceEventNotFoundError(
            f"No documented_care_sessions record found for service_event_id={service_event_id}"
        )
    session, shift, location, recipient = row

    # 2 — Resolve ISP goal UUIDs → goal descriptions (skipped when no goals recorded)
    goal_descriptions: list[str] = []
    if session.goals_addressed_in_session:
        try:
            goal_result = await db.execute(
                select(SupportPlanGoal.goal_description)
                .where(SupportPlanGoal.goal_id.in_(session.goals_addressed_in_session))
                .where(SupportPlanGoal.is_currently_active.is_(True))
            )
            goal_descriptions = list(goal_result.scalars().all())
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError(
                f"Goals query failed for service_event_id={service_event_id}: {exc}"
            ) from exc

    # 3 — MAR records joined with prescribed_medications (empty list is valid)
    try:
        mar_result = await db.execute(
            select(MedicationAdministrationRecord, PrescribedMedication)
            .join(
                PrescribedMedication,
                MedicationAdministrationRecord.medication_id == PrescribedMedication.medication_id,
            )
            .where(MedicationAdministrationRecord.care_session_id == service_event_id)
        )
        mar_rows = list(mar_result.all())
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError(
            f"MAR query failed for service_event_id={service_event_id}: {exc}"
        ) from exc

    # 4 — Mock Medicaid authorization API
    try:
        response = await http_client.post(
            f"{auth_api_url}/authorization",
            json={
                "patient_name": recipient.full_name,
                "insurance_number": recipient.medicaid_id,
            },
            timeout=auth_api_timeout,
        )
        response.raise_for_status()
        auth_data = response.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise AuthAPIUnavailableError(
            f"Mock auth API unreachable at {auth_api_url}: {exc}"
        ) from exc

    # Compute billable units from duration if Pipeline A left it null (15-min units)
    service_units = session.billable_units_calculated
    if service_units is None and session.total_duration_minutes:
        service_units = session.total_duration_minutes // 15

    # Default EVV GPS to org location if Pipeline A did not populate coordinates
    _ORG_LAT, _ORG_LNG = 39.099728, -94.578568
    evv_checkin_lat = (
        float(session.checkin_location_latitude)
        if session.checkin_location_latitude is not None else _ORG_LAT
    )
    evv_checkin_lng = (
        float(session.checkin_location_longitude)
        if session.checkin_location_longitude is not None else _ORG_LNG
    )
    evv_checkout_lat = (
        float(session.checkout_location_latitude)
        if session.checkout_location_latitude is not None else _ORG_LAT
    )
    evv_checkout_lng = (
        float(session.checkout_location_longitude)
        if session.checkout_location_longitude is not None else _ORG_LNG
    )

    # Derive "HH:MM-HH:MM" activity_time string from actual clock times (UTC)
    if session.actual_clock_in_time and session.actual_clock_out_time:
        activity_time = (
            f"{session.actual_clock_in_time.strftime('%H:%M')}"
            f"-{session.actual_clock_out_time.strftime('%H:%M')}"
        )
    else:
        activity_time = None

    return EnrichedServiceEvent(
        # identity
        service_event_id=session.care_session_id,

        # from care_recipients
        participant_name=recipient.full_name,
        participant_dcn=recipient.medicaid_id,
        participant_dob=recipient.date_of_birth,
        sex=recipient.sex,

        # from staff_shift_assignments + service_locations
        service_date=shift.shift_date,
        service_location=location.service_location_name,
        provider_name=shift.direct_support_professional_name,
        procedure_code=shift.service_billing_code,
        rendering_npi=location.rendering_npi,
        modifier_1=location.modifier_1,
        modifier_2=location.modifier_2,
        modifier_3=location.modifier_3,

        # from documented_care_sessions
        begin_time=session.actual_clock_in_time.time() if session.actual_clock_in_time else None,
        end_time=session.actual_clock_out_time.time() if session.actual_clock_out_time else None,
        provider_signature="signed" if session.dsp_has_signed else "unsigned",
        service_description=session.care_session_narrative or "",
        activity_time=activity_time,
        activity_category=_BILLING_CODE_TO_CATEGORY.get(shift.service_billing_code),
        participation_level=session.recipient_engagement_notes or "",
        support_level=session.level_of_support_provided or "",
        goals_supported=goal_descriptions,
        health_observations=session.health_observations_notes,
        behavioral_notes=session.behavioral_observations_notes,
        community_activity=session.community_outing_notes,
        meal_type=", ".join(session.meals_provided) if session.meals_provided else None,
        personal_care_type=", ".join(session.personal_care_activities) if session.personal_care_activities else None,

        # EVV from documented_care_sessions (defaults to org coords if Pipeline A omitted them)
        evv_checkin_lat=evv_checkin_lat,
        evv_checkin_lng=evv_checkin_lng,
        evv_checkout_lat=evv_checkout_lat,
        evv_checkout_lng=evv_checkout_lng,
        evv_caregiver_id=None,  # not in schema.sql

        # billing metadata
        diagnosis_code=recipient.primary_diagnosis_code,
        waiver_identifier=recipient.waiver_program,
        duration_minutes=session.total_duration_minutes or 0,
        service_units=service_units or 0,
        authorization_number=None,  # not in schema.sql
        flags=[{"message": f} for f in (session.documentation_gap_flags or [])],
        overall_confidence=session.ai_confidence_rating or "Medium",

        # MAR: resolved from medication_administration_records + prescribed_medications JOIN
        mar_records=[
            MARRecord(
                id=mar_rec.administration_record_id,
                service_event_id=mar_rec.care_session_id,
                med_name=med.medication_name,
                med_dosage=med.dosage_amount,
                med_time_administered=mar_rec.actual_administration_time.time() if mar_rec.actual_administration_time else None,
                variance_code=mar_rec.reason_if_not_given if not mar_rec.was_medication_given else None,
            )
            for mar_rec, med in mar_rows
        ],

        # mock Medicaid authorization API
        authorization=AuthorizationDetails(**auth_data),
    )
