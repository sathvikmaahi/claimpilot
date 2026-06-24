"""
Seed script — populates all Pipeline A schema.sql tables with 6 mock patients.

Patient keys match mock-medicaid-api/data.py exactly so auth API lookups succeed:
  John Smith    / MO100001 — valid auth, clean pass
  Maria Garcia  / MO100002 — units exhausted (CO-151)
  David Lee     / MO100003 — expired auth (CO-197)
  Susan Brown   / MO100004 — service code mismatch
  James Wilson  / MO100005 — waiver type mismatch
  Linda Martinez/ MO100006 — valid auth, clean pass

SESSION_UUIDS (= documented_care_sessions.care_session_id) are preserved from the
original seed so that any existing API client calls continue to work unchanged.
David Lee and James Wilson have no MAR records — tests the empty-MAR path.

Run from src/:
  python scripts/seed_pipeline_a.py
"""
import asyncio
import uuid
from datetime import date, time, datetime, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from db.session import Base, async_session_factory, engine
from db.models.pipeline_a import (
    CareRecipient,
    StaffShiftAssignment,
    DocumentedCareSession,
    PrescribedMedication,
    MedicationAdministrationRecord,
    SupportPlanGoal,
)
from db.models.claims import Claim  # noqa: F401 — ensures claims table is created

# ─── Fixed UUIDs — all seeds are deterministic and idempotent ─────────────────

# Preserved from original seed: used as service_event_id throughout Pipeline B
SESSION_UUIDS = {
    "john_smith":     uuid.UUID("11111111-1111-1111-1111-111111111111"),
    "maria_garcia":   uuid.UUID("22222222-2222-2222-2222-222222222222"),
    "david_lee":      uuid.UUID("33333333-3333-3333-3333-333333333333"),
    "susan_brown":    uuid.UUID("44444444-4444-4444-4444-444444444444"),
    "james_wilson":   uuid.UUID("55555555-5555-5555-5555-555555555555"),
    "linda_martinez": uuid.UUID("66666666-6666-6666-6666-666666666666"),
}

PATIENT_UUIDS = {
    "john_smith":     uuid.UUID("a1111111-1111-1111-1111-111111111111"),
    "maria_garcia":   uuid.UUID("a2222222-2222-2222-2222-222222222222"),
    "david_lee":      uuid.UUID("a3333333-3333-3333-3333-333333333333"),
    "susan_brown":    uuid.UUID("a4444444-4444-4444-4444-444444444444"),
    "james_wilson":   uuid.UUID("a5555555-5555-5555-5555-555555555555"),
    "linda_martinez": uuid.UUID("a6666666-6666-6666-6666-666666666666"),
}

SHIFT_UUIDS = {
    "john_smith":     uuid.UUID("b1111111-1111-1111-1111-111111111111"),
    "maria_garcia":   uuid.UUID("b2222222-2222-2222-2222-222222222222"),
    "david_lee":      uuid.UUID("b3333333-3333-3333-3333-333333333333"),
    "susan_brown":    uuid.UUID("b4444444-4444-4444-4444-444444444444"),
    "james_wilson":   uuid.UUID("b5555555-5555-5555-5555-555555555555"),
    "linda_martinez": uuid.UUID("b6666666-6666-6666-6666-666666666666"),
}

GOAL_UUIDS = {
    # John Smith
    "john_adl":          uuid.UUID("d1111111-1111-1111-1111-000000000001"),
    "john_meal":         uuid.UUID("d1111111-1111-1111-1111-000000000002"),
    "john_community":    uuid.UUID("d1111111-1111-1111-1111-000000000003"),
    # Maria Garcia
    "maria_adl":         uuid.UUID("d2222222-2222-2222-2222-000000000001"),
    "maria_meal":        uuid.UUID("d2222222-2222-2222-2222-000000000002"),
    "maria_living":      uuid.UUID("d2222222-2222-2222-2222-000000000003"),
    # David Lee
    "david_adl":         uuid.UUID("d3333333-3333-3333-3333-000000000001"),
    "david_living":      uuid.UUID("d3333333-3333-3333-3333-000000000002"),
    # Susan Brown
    "susan_adl":         uuid.UUID("d4444444-4444-4444-4444-000000000001"),
    "susan_meal":        uuid.UUID("d4444444-4444-4444-4444-000000000002"),
    # James Wilson
    "james_adl":         uuid.UUID("d5555555-5555-5555-5555-000000000001"),
    "james_community":   uuid.UUID("d5555555-5555-5555-5555-000000000002"),
    # Linda Martinez
    "linda_adl":         uuid.UUID("d6666666-6666-6666-6666-000000000001"),
    "linda_meal":        uuid.UUID("d6666666-6666-6666-6666-000000000002"),
    "linda_community":   uuid.UUID("d6666666-6666-6666-6666-000000000003"),
}

MED_UUIDS = {
    "john_metformin":      uuid.UUID("e1111111-1111-1111-1111-111111111111"),
    "maria_lisinopril":    uuid.UUID("e2222222-2222-2222-2222-111111111111"),
    "maria_atorvastatin":  uuid.UUID("e2222222-2222-2222-2222-222222222222"),
    "susan_risperidone":   uuid.UUID("e4444444-4444-4444-4444-111111111111"),
    "linda_sertraline":    uuid.UUID("e6666666-6666-6666-6666-111111111111"),
}

# Kansas City area EVV coordinates (Liberty House and Sunrise Home)
KC_LAT, KC_LNG = 39.0997, -94.5786

# Common date / time constants for 2026-06-10 shift
SHIFT_DATE = date(2026, 6, 10)
CLOCK_IN   = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
CLOCK_OUT  = datetime(2026, 6, 10, 15, 0, 0, tzinfo=timezone.utc)

# ─── Table data ───────────────────────────────────────────────────────────────

CARE_RECIPIENTS = [
    dict(
        care_recipient_id=PATIENT_UUIDS["john_smith"],
        full_name="John Smith",
        medicaid_id="MO100001",
        date_of_birth=date(1982, 3, 14),
        waiver_program="Comprehensive",
        primary_diagnosis_code="F70",
    ),
    dict(
        care_recipient_id=PATIENT_UUIDS["maria_garcia"],
        full_name="Maria Garcia",
        medicaid_id="MO100002",
        date_of_birth=date(1975, 7, 22),
        waiver_program="Comprehensive",
        primary_diagnosis_code="F71",
    ),
    dict(
        care_recipient_id=PATIENT_UUIDS["david_lee"],
        full_name="David Lee",
        medicaid_id="MO100003",
        date_of_birth=date(1990, 11, 5),
        waiver_program="Comprehensive",
        primary_diagnosis_code="F70",
    ),
    dict(
        care_recipient_id=PATIENT_UUIDS["susan_brown"],
        full_name="Susan Brown",
        medicaid_id="MO100004",
        date_of_birth=date(1968, 4, 30),
        waiver_program="Comprehensive",
        primary_diagnosis_code="F72",
    ),
    dict(
        care_recipient_id=PATIENT_UUIDS["james_wilson"],
        full_name="James Wilson",
        medicaid_id="MO100005",
        date_of_birth=date(1985, 9, 18),
        waiver_program="Partnership for Hope",  # waiver mismatch scenario — T2016 ISL requires Comprehensive
        primary_diagnosis_code="F84",
    ),
    dict(
        care_recipient_id=PATIENT_UUIDS["linda_martinez"],
        full_name="Linda Martinez",
        medicaid_id="MO100006",
        date_of_birth=date(1978, 12, 3),
        waiver_program="Comprehensive",
        primary_diagnosis_code="F70",
    ),
]

SUPPORT_PLAN_GOALS = [
    # John Smith
    dict(goal_id=GOAL_UUIDS["john_adl"],       care_recipient_id=PATIENT_UUIDS["john_smith"],
         goal_category="daily_living",          goal_description="Develop independence in morning ADL routine with minimal prompting", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["john_meal"],       care_recipient_id=PATIENT_UUIDS["john_smith"],
         goal_category="daily_living",          goal_description="Prepare breakfast and simple meals with verbal guidance", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["john_community"],  care_recipient_id=PATIENT_UUIDS["john_smith"],
         goal_category="community_integration", goal_description="Participate in at least one community outing per week", is_currently_active=True),
    # Maria Garcia
    dict(goal_id=GOAL_UUIDS["maria_adl"],       care_recipient_id=PATIENT_UUIDS["maria_garcia"],
         goal_category="daily_living",          goal_description="Complete morning personal care routine with physical assistance", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["maria_meal"],      care_recipient_id=PATIENT_UUIDS["maria_garcia"],
         goal_category="daily_living",          goal_description="Assist with meal preparation using adaptive equipment", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["maria_living"],    care_recipient_id=PATIENT_UUIDS["maria_garcia"],
         goal_category="daily_living",          goal_description="Build daily living skills for greater independence", is_currently_active=True),
    # David Lee
    dict(goal_id=GOAL_UUIDS["david_adl"],       care_recipient_id=PATIENT_UUIDS["david_lee"],
         goal_category="daily_living",          goal_description="Maintain morning routine independently with minimal verbal prompts", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["david_living"],    care_recipient_id=PATIENT_UUIDS["david_lee"],
         goal_category="daily_living",          goal_description="Practice independent living skills including laundry and meal prep", is_currently_active=True),
    # Susan Brown
    dict(goal_id=GOAL_UUIDS["susan_adl"],       care_recipient_id=PATIENT_UUIDS["susan_brown"],
         goal_category="daily_living",          goal_description="Complete morning ADL routine with full physical support", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["susan_meal"],      care_recipient_id=PATIENT_UUIDS["susan_brown"],
         goal_category="daily_living",          goal_description="Participate in meal preparation with hand-over-hand assistance", is_currently_active=True),
    # James Wilson
    dict(goal_id=GOAL_UUIDS["james_adl"],       care_recipient_id=PATIENT_UUIDS["james_wilson"],
         goal_category="daily_living",          goal_description="Complete morning routine with verbal prompts", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["james_community"], care_recipient_id=PATIENT_UUIDS["james_wilson"],
         goal_category="community_integration", goal_description="Engage in at least two community activities per week", is_currently_active=True),
    # Linda Martinez
    dict(goal_id=GOAL_UUIDS["linda_adl"],       care_recipient_id=PATIENT_UUIDS["linda_martinez"],
         goal_category="daily_living",          goal_description="Build independence in morning ADL routine", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["linda_meal"],      care_recipient_id=PATIENT_UUIDS["linda_martinez"],
         goal_category="daily_living",          goal_description="Prepare meals with decreasing levels of assistance", is_currently_active=True),
    dict(goal_id=GOAL_UUIDS["linda_community"], care_recipient_id=PATIENT_UUIDS["linda_martinez"],
         goal_category="community_integration", goal_description="Participate in community activities and library programs", is_currently_active=True),
]

PRESCRIBED_MEDICATIONS = [
    dict(
        medication_id=MED_UUIDS["john_metformin"],
        care_recipient_id=PATIENT_UUIDS["john_smith"],
        medication_name="Metformin",
        dosage_amount="500mg",
        administration_route="oral",
        scheduled_time_of_day=time(8, 0, 0),
        is_currently_active=True,
    ),
    dict(
        medication_id=MED_UUIDS["maria_lisinopril"],
        care_recipient_id=PATIENT_UUIDS["maria_garcia"],
        medication_name="Lisinopril",
        dosage_amount="10mg",
        administration_route="oral",
        scheduled_time_of_day=time(8, 0, 0),
        is_currently_active=True,
    ),
    dict(
        medication_id=MED_UUIDS["maria_atorvastatin"],
        care_recipient_id=PATIENT_UUIDS["maria_garcia"],
        medication_name="Atorvastatin",
        dosage_amount="20mg",
        administration_route="oral",
        scheduled_time_of_day=time(12, 0, 0),
        is_currently_active=True,
    ),
    dict(
        medication_id=MED_UUIDS["susan_risperidone"],
        care_recipient_id=PATIENT_UUIDS["susan_brown"],
        medication_name="Risperidone",
        dosage_amount="1mg",
        administration_route="oral",
        scheduled_time_of_day=time(8, 0, 0),
        is_currently_active=True,
    ),
    dict(
        medication_id=MED_UUIDS["linda_sertraline"],
        care_recipient_id=PATIENT_UUIDS["linda_martinez"],
        medication_name="Sertraline",
        dosage_amount="50mg",
        administration_route="oral",
        scheduled_time_of_day=time(8, 0, 0),
        is_currently_active=True,
    ),
    # David Lee and James Wilson have no prescribed medications — tests empty-MAR path
]

STAFF_SHIFT_ASSIGNMENTS = [
    dict(
        shift_assignment_id=SHIFT_UUIDS["john_smith"],
        care_recipient_id=PATIENT_UUIDS["john_smith"],
        direct_support_professional_name="Jane Doe",
        service_location_name="Liberty House",
        shift_date=SHIFT_DATE,
        scheduled_start_time=time(7, 0, 0),
        scheduled_end_time=time(15, 0, 0),
        service_billing_code="T2016",
    ),
    dict(
        shift_assignment_id=SHIFT_UUIDS["maria_garcia"],
        care_recipient_id=PATIENT_UUIDS["maria_garcia"],
        direct_support_professional_name="Jane Doe",
        service_location_name="Liberty House",
        shift_date=SHIFT_DATE,
        scheduled_start_time=time(7, 0, 0),
        scheduled_end_time=time(15, 0, 0),
        service_billing_code="T2016",
    ),
    dict(
        shift_assignment_id=SHIFT_UUIDS["david_lee"],
        care_recipient_id=PATIENT_UUIDS["david_lee"],
        direct_support_professional_name="Mark Johnson",
        service_location_name="Sunrise Home",
        shift_date=SHIFT_DATE,
        scheduled_start_time=time(7, 0, 0),
        scheduled_end_time=time(15, 0, 0),
        service_billing_code="T2016",
    ),
    dict(
        shift_assignment_id=SHIFT_UUIDS["susan_brown"],
        care_recipient_id=PATIENT_UUIDS["susan_brown"],
        direct_support_professional_name="Mark Johnson",
        service_location_name="Sunrise Home",
        shift_date=SHIFT_DATE,
        scheduled_start_time=time(7, 0, 0),
        scheduled_end_time=time(15, 0, 0),
        service_billing_code="T2016",
    ),
    dict(
        shift_assignment_id=SHIFT_UUIDS["james_wilson"],
        care_recipient_id=PATIENT_UUIDS["james_wilson"],
        direct_support_professional_name="Jane Doe",
        service_location_name="Liberty House",
        shift_date=SHIFT_DATE,
        scheduled_start_time=time(7, 0, 0),
        scheduled_end_time=time(15, 0, 0),
        service_billing_code="T2016",
    ),
    dict(
        shift_assignment_id=SHIFT_UUIDS["linda_martinez"],
        care_recipient_id=PATIENT_UUIDS["linda_martinez"],
        direct_support_professional_name="Jane Doe",
        service_location_name="Liberty House",
        shift_date=SHIFT_DATE,
        scheduled_start_time=time(7, 0, 0),
        scheduled_end_time=time(15, 0, 0),
        service_billing_code="T2016",
    ),
]

DOCUMENTED_CARE_SESSIONS = [
    dict(
        care_session_id=SESSION_UUIDS["john_smith"],
        shift_assignment_id=SHIFT_UUIDS["john_smith"],
        care_recipient_id=PATIENT_UUIDS["john_smith"],
        actual_clock_in_time=CLOCK_IN,
        actual_clock_out_time=CLOCK_OUT,
        total_duration_minutes=480,
        billable_units_calculated=32,
        care_session_narrative="Assisted with morning ADL routine including bathing, dressing, and grooming. Prepared breakfast. Administered morning medications. Supported community outing to grocery store.",
        activities_performed=["morning_adl_routine", "bathing_dressing_grooming", "breakfast_preparation", "medication_administration", "community_outing"],
        level_of_support_provided="verbal_prompts",
        recipient_engagement_notes="Active participation with verbal prompts on most tasks",
        health_observations_notes=None,
        behavioral_observations_notes=None,
        community_outing_notes="Grocery store outing",
        meals_provided=["breakfast"],
        personal_care_activities=["bathing"],
        goals_addressed_in_session=[GOAL_UUIDS["john_adl"], GOAL_UUIDS["john_meal"], GOAL_UUIDS["john_community"]],
        checkin_location_latitude=KC_LAT,
        checkin_location_longitude=KC_LNG,
        checkout_location_latitude=KC_LAT,
        checkout_location_longitude=KC_LNG,
        ai_confidence_rating="High",
        documentation_gap_flags=[],
        dsp_has_signed=True,
        session_status="ready_for_billing",
        goals_resolution=None,
    ),
    dict(
        care_session_id=SESSION_UUIDS["maria_garcia"],
        shift_assignment_id=SHIFT_UUIDS["maria_garcia"],
        care_recipient_id=PATIENT_UUIDS["maria_garcia"],
        actual_clock_in_time=CLOCK_IN,
        actual_clock_out_time=CLOCK_OUT,
        total_duration_minutes=480,
        billable_units_calculated=32,
        care_session_narrative="Assisted with morning personal care. Prepared breakfast and lunch. Administered morning and noon medications. Supported skills development activities.",
        activities_performed=["morning_personal_care", "breakfast_lunch_preparation", "medication_administration", "skills_development_activities"],
        level_of_support_provided="physical_assistance",
        recipient_engagement_notes="Required moderate physical assistance for personal care",
        health_observations_notes=None,
        behavioral_observations_notes=None,
        community_outing_notes=None,
        meals_provided=["breakfast", "lunch"],
        personal_care_activities=["grooming"],
        goals_addressed_in_session=[GOAL_UUIDS["maria_adl"], GOAL_UUIDS["maria_meal"], GOAL_UUIDS["maria_living"]],
        checkin_location_latitude=KC_LAT,
        checkin_location_longitude=KC_LNG,
        checkout_location_latitude=KC_LAT,
        checkout_location_longitude=KC_LNG,
        ai_confidence_rating="Medium",
        documentation_gap_flags=["Authorization units may be exhausted"],
        dsp_has_signed=True,
        session_status="ready_for_billing",
        goals_resolution=None,
    ),
    dict(
        care_session_id=SESSION_UUIDS["david_lee"],
        shift_assignment_id=SHIFT_UUIDS["david_lee"],
        care_recipient_id=PATIENT_UUIDS["david_lee"],
        actual_clock_in_time=CLOCK_IN,
        actual_clock_out_time=CLOCK_OUT,
        total_duration_minutes=480,
        billable_units_calculated=32,
        care_session_narrative="Assisted with morning routine and personal care. Meal preparation for breakfast. Supported independent living skills. Afternoon leisure activities.",
        activities_performed=["morning_routine", "breakfast_preparation", "independent_living_skills", "leisure_activities"],
        level_of_support_provided="verbal_prompts",
        recipient_engagement_notes="Largely independent with minimal prompting",
        health_observations_notes=None,
        behavioral_observations_notes=None,
        community_outing_notes=None,
        meals_provided=["breakfast"],
        personal_care_activities=["dressing"],
        goals_addressed_in_session=[GOAL_UUIDS["david_adl"], GOAL_UUIDS["david_living"]],
        checkin_location_latitude=KC_LAT,
        checkin_location_longitude=KC_LNG,
        checkout_location_latitude=KC_LAT,
        checkout_location_longitude=KC_LNG,
        ai_confidence_rating="Low",
        documentation_gap_flags=["Patient authorization may be expired"],
        dsp_has_signed=True,
        session_status="ready_for_billing",
        goals_resolution=None,
    ),
    dict(
        care_session_id=SESSION_UUIDS["susan_brown"],
        shift_assignment_id=SHIFT_UUIDS["susan_brown"],
        care_recipient_id=PATIENT_UUIDS["susan_brown"],
        actual_clock_in_time=CLOCK_IN,
        actual_clock_out_time=CLOCK_OUT,
        total_duration_minutes=480,
        billable_units_calculated=32,
        care_session_narrative="Full support with morning ADL routine. Meal preparation and feeding assistance. Administered medications. Afternoon sensory activities.",
        activities_performed=["morning_adl_full_support", "meal_preparation_feeding_assistance", "medication_administration", "sensory_activities"],
        level_of_support_provided="full_support",
        recipient_engagement_notes="Full physical support required for all tasks",
        health_observations_notes=None,
        behavioral_observations_notes=None,
        community_outing_notes=None,
        meals_provided=["breakfast"],
        personal_care_activities=["toileting", "bathing"],
        goals_addressed_in_session=[GOAL_UUIDS["susan_adl"], GOAL_UUIDS["susan_meal"]],
        checkin_location_latitude=KC_LAT,
        checkin_location_longitude=KC_LNG,
        checkout_location_latitude=KC_LAT,
        checkout_location_longitude=KC_LNG,
        ai_confidence_rating="Low",
        documentation_gap_flags=["Possible service code mismatch with authorization"],
        dsp_has_signed=True,
        session_status="ready_for_billing",
        goals_resolution=None,
    ),
    dict(
        care_session_id=SESSION_UUIDS["james_wilson"],
        shift_assignment_id=SHIFT_UUIDS["james_wilson"],
        care_recipient_id=PATIENT_UUIDS["james_wilson"],
        actual_clock_in_time=CLOCK_IN,
        actual_clock_out_time=CLOCK_OUT,
        total_duration_minutes=480,
        billable_units_calculated=32,
        care_session_narrative="Assisted with morning routine and personal care. Breakfast preparation. Medication administration. Community outing to local park.",
        activities_performed=["morning_routine", "breakfast_preparation", "medication_administration", "community_outing_park"],
        level_of_support_provided="verbal_prompts",
        recipient_engagement_notes="Active participation with verbal prompts",
        health_observations_notes=None,
        behavioral_observations_notes=None,
        community_outing_notes="Local park outing",
        meals_provided=["breakfast"],
        personal_care_activities=["grooming"],
        goals_addressed_in_session=[GOAL_UUIDS["james_adl"], GOAL_UUIDS["james_community"]],
        checkin_location_latitude=KC_LAT,
        checkin_location_longitude=KC_LNG,
        checkout_location_latitude=KC_LAT,
        checkout_location_longitude=KC_LNG,
        ai_confidence_rating="Low",
        documentation_gap_flags=["Waiver type mismatch with authorization"],
        dsp_has_signed=True,
        session_status="ready_for_billing",
        goals_resolution=None,
    ),
    dict(
        care_session_id=SESSION_UUIDS["linda_martinez"],
        shift_assignment_id=SHIFT_UUIDS["linda_martinez"],
        care_recipient_id=PATIENT_UUIDS["linda_martinez"],
        actual_clock_in_time=CLOCK_IN,
        actual_clock_out_time=CLOCK_OUT,
        total_duration_minutes=480,
        billable_units_calculated=32,
        care_session_narrative="Supported morning ADL routine. Meal preparation assistance. Medication administration. Skills development and community integration activities.",
        activities_performed=["morning_adl_routine", "meal_preparation_assistance", "medication_administration", "skills_development", "community_integration"],
        level_of_support_provided="verbal_prompts",
        recipient_engagement_notes="Active participation with occasional verbal prompts",
        health_observations_notes=None,
        behavioral_observations_notes=None,
        community_outing_notes="Library visit",
        meals_provided=["breakfast"],
        personal_care_activities=["dressing"],
        goals_addressed_in_session=[GOAL_UUIDS["linda_adl"], GOAL_UUIDS["linda_meal"], GOAL_UUIDS["linda_community"]],
        checkin_location_latitude=KC_LAT,
        checkin_location_longitude=KC_LNG,
        checkout_location_latitude=KC_LAT,
        checkout_location_longitude=KC_LNG,
        ai_confidence_rating="High",
        documentation_gap_flags=[],
        dsp_has_signed=True,
        session_status="ready_for_billing",
        goals_resolution=None,
    ),
]

MAR_RECORDS = [
    dict(
        administration_record_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        care_session_id=SESSION_UUIDS["john_smith"],
        medication_id=MED_UUIDS["john_metformin"],
        was_medication_given=True,
        actual_administration_time=datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc),
        reason_if_not_given=None,
    ),
    dict(
        administration_record_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        care_session_id=SESSION_UUIDS["maria_garcia"],
        medication_id=MED_UUIDS["maria_lisinopril"],
        was_medication_given=True,
        actual_administration_time=datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc),
        reason_if_not_given=None,
    ),
    dict(
        administration_record_id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        care_session_id=SESSION_UUIDS["maria_garcia"],
        medication_id=MED_UUIDS["maria_atorvastatin"],
        was_medication_given=True,
        actual_administration_time=datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        reason_if_not_given=None,
    ),
    dict(
        administration_record_id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        care_session_id=SESSION_UUIDS["susan_brown"],
        medication_id=MED_UUIDS["susan_risperidone"],
        was_medication_given=True,
        actual_administration_time=datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc),
        reason_if_not_given=None,
    ),
    dict(
        administration_record_id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        care_session_id=SESSION_UUIDS["linda_martinez"],
        medication_id=MED_UUIDS["linda_sertraline"],
        was_medication_given=True,
        actual_administration_time=datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc),
        reason_if_not_given=None,
    ),
    # David Lee and James Wilson have no MAR rows — tests the empty-MAR path
]


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Clear in FK-safe order:
        # 1. MAR records (FK to documented_care_sessions)
        # 2. documented_care_sessions (FK to staff_shift_assignments + care_recipients, both RESTRICT)
        # 3. staff_shift_assignments, support_plan_goals, prescribed_medications (FK to care_recipients)
        # 4. care_recipients (no outgoing FKs)
        await session.execute(delete(MedicationAdministrationRecord))
        await session.execute(delete(DocumentedCareSession))
        await session.execute(delete(StaffShiftAssignment))
        await session.execute(delete(SupportPlanGoal))
        await session.execute(delete(PrescribedMedication))
        await session.execute(delete(CareRecipient))
        await session.flush()

        # Insert in FK-safe order (ON CONFLICT DO NOTHING makes re-runs safe)
        await session.execute(insert(CareRecipient).values(CARE_RECIPIENTS).on_conflict_do_nothing())
        await session.execute(insert(PrescribedMedication).values(PRESCRIBED_MEDICATIONS).on_conflict_do_nothing())
        await session.execute(insert(SupportPlanGoal).values(SUPPORT_PLAN_GOALS).on_conflict_do_nothing())
        await session.execute(insert(StaffShiftAssignment).values(STAFF_SHIFT_ASSIGNMENTS).on_conflict_do_nothing())
        await session.execute(insert(DocumentedCareSession).values(DOCUMENTED_CARE_SESSIONS).on_conflict_do_nothing())
        await session.execute(insert(MedicationAdministrationRecord).values(MAR_RECORDS).on_conflict_do_nothing())

        await session.commit()
        print(
            f"Seeded {len(CARE_RECIPIENTS)} patients, "
            f"{len(SUPPORT_PLAN_GOALS)} goals, "
            f"{len(PRESCRIBED_MEDICATIONS)} medications, "
            f"{len(STAFF_SHIFT_ASSIGNMENTS)} shifts, "
            f"{len(DOCUMENTED_CARE_SESSIONS)} care sessions, "
            f"{len(MAR_RECORDS)} MAR records."
        )


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
