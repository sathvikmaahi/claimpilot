"""
Seed script — populates all 3 Pipeline A tables with 6 mock patients.

Patient keys match mock-medicaid-api/data.py exactly so auth API lookups succeed:
  John Smith / MO100001 — valid auth, clean pass
  Maria Garcia / MO100002 — units exhausted (CO-151 scenario)
  David Lee / MO100003 — expired auth
  Susan Brown / MO100004 — service code mismatch
  James Wilson / MO100005 — waiver type mismatch
  Linda Martinez / MO100006 — valid auth, clean pass (second patient)

Run from src/Clerk_Assistance_Pipeline/:
  python scripts/seed_pipeline_a.py
"""
import asyncio
import uuid
from datetime import date, time

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from db.session import Base, async_session_factory, engine
from db.models.pipeline_a import ProgressNote, MAR, ServiceMetadata
from db.models.claims import Claim  # noqa: F401 — ensures claims table is created too

# Fixed UUIDs so the seed is idempotent and deterministic
UUIDS = {
    "john_smith":     uuid.UUID("11111111-1111-1111-1111-111111111111"),
    "maria_garcia":   uuid.UUID("22222222-2222-2222-2222-222222222222"),
    "david_lee":      uuid.UUID("33333333-3333-3333-3333-333333333333"),
    "susan_brown":    uuid.UUID("44444444-4444-4444-4444-444444444444"),
    "james_wilson":   uuid.UUID("55555555-5555-5555-5555-555555555555"),
    "linda_martinez": uuid.UUID("66666666-6666-6666-6666-666666666666"),
}

# Kansas City area EVV coordinates
KC_LAT, KC_LNG = 39.0997, -94.5786

PROGRESS_NOTES = [
    dict(
        service_event_id=UUIDS["john_smith"],
        participant_name="John Smith",
        participant_dcn="MO100001",
        participant_dob=date(1982, 3, 14),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Liberty House",
        provider_name="Jane Doe",
        provider_signature="jdoe",
        service_description="Assisted with morning ADL routine including bathing, dressing, and grooming. Prepared breakfast. Administered morning medications. Supported community outing to grocery store.",
        activity_time="07:00-15:00",
        participation_level="Active participation with verbal prompts on most tasks",
        support_level="verbal",
        goals_supported=["morning_adl", "meal_prep", "community_integration"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity="Grocery store outing",
        meal_type="breakfast",
        personal_care_type="bathing",
    ),
    dict(
        service_event_id=UUIDS["maria_garcia"],
        participant_name="Maria Garcia",
        participant_dcn="MO100002",
        participant_dob=date(1975, 7, 22),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Liberty House",
        provider_name="Jane Doe",
        provider_signature="jdoe",
        service_description="Assisted with morning personal care. Prepared breakfast and lunch. Administered morning and noon medications. Supported skills development activities.",
        activity_time="07:00-15:00",
        participation_level="Required moderate physical assistance for personal care",
        support_level="physical",
        goals_supported=["morning_adl", "meal_prep", "daily_living_skills"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity=None,
        meal_type="breakfast",
        personal_care_type="grooming",
    ),
    dict(
        service_event_id=UUIDS["david_lee"],
        participant_name="David Lee",
        participant_dcn="MO100003",
        participant_dob=date(1990, 11, 5),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Sunrise Home",
        provider_name="Mark Johnson",
        provider_signature="mjohnson",
        service_description="Assisted with morning routine and personal care. Meal preparation for breakfast. Supported independent living skills. Afternoon leisure activities.",
        activity_time="07:00-15:00",
        participation_level="Largely independent with minimal prompting",
        support_level="verbal",
        goals_supported=["morning_adl", "independent_living"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity=None,
        meal_type="breakfast",
        personal_care_type="dressing",
    ),
    dict(
        service_event_id=UUIDS["susan_brown"],
        participant_name="Susan Brown",
        participant_dcn="MO100004",
        participant_dob=date(1968, 4, 30),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Sunrise Home",
        provider_name="Mark Johnson",
        provider_signature="mjohnson",
        service_description="Full support with morning ADL routine. Meal preparation and feeding assistance. Administered medications. Afternoon sensory activities.",
        activity_time="07:00-15:00",
        participation_level="Full physical support required for all tasks",
        support_level="full",
        goals_supported=["morning_adl", "meal_prep"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity=None,
        meal_type="breakfast",
        personal_care_type="toileting",
    ),
    dict(
        service_event_id=UUIDS["james_wilson"],
        participant_name="James Wilson",
        participant_dcn="MO100005",
        participant_dob=date(1985, 9, 18),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Liberty House",
        provider_name="Jane Doe",
        provider_signature="jdoe",
        service_description="Assisted with morning routine and personal care. Breakfast preparation. Medication administration. Community outing to local park.",
        activity_time="07:00-15:00",
        participation_level="Active participation with verbal prompts",
        support_level="verbal",
        goals_supported=["morning_adl", "community_integration"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity="Local park outing",
        meal_type="breakfast",
        personal_care_type="grooming",
    ),
    dict(
        service_event_id=UUIDS["linda_martinez"],
        participant_name="Linda Martinez",
        participant_dcn="MO100006",
        participant_dob=date(1978, 12, 3),
        service_date=date(2026, 6, 10),
        begin_time=time(7, 0, 0),
        end_time=time(15, 0, 0),
        service_location="Liberty House",
        provider_name="Jane Doe",
        provider_signature="jdoe",
        service_description="Supported morning ADL routine. Meal preparation assistance. Medication administration. Skills development and community integration activities.",
        activity_time="07:00-15:00",
        participation_level="Active participation with occasional verbal prompts",
        support_level="verbal",
        goals_supported=["morning_adl", "meal_prep", "community_integration"],
        activity_category="Residential Habilitation",
        health_observations=None,
        behavioral_notes=None,
        community_activity="Library visit",
        meal_type="breakfast",
        personal_care_type="dressing",
    ),
]

SERVICE_METADATA = [
    dict(
        service_event_id=UUIDS["john_smith"],
        evv_checkin_lat=KC_LAT, evv_checkin_lng=KC_LNG,
        evv_checkout_lat=KC_LAT, evv_checkout_lng=KC_LNG,
        evv_caregiver_id="DSP-001",
        diagnosis_code="F70",
        waiver_identifier="Comprehensive",
        duration_minutes=480,
        service_units=32,
        rendering_npi="1234567890",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None, modifier_3=None,
        authorization_number="DSP-AUTH-2026-001",
        flags=[],
        overall_confidence="High",
    ),
    dict(
        service_event_id=UUIDS["maria_garcia"],
        evv_checkin_lat=KC_LAT, evv_checkin_lng=KC_LNG,
        evv_checkout_lat=KC_LAT, evv_checkout_lng=KC_LNG,
        evv_caregiver_id="DSP-001",
        diagnosis_code="F71",
        waiver_identifier="Comprehensive",
        duration_minutes=480,
        service_units=32,
        rendering_npi="1234567890",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None, modifier_3=None,
        authorization_number="DSP-AUTH-2026-002",
        flags=[{"flag_type": "units_risk", "message": "Authorization units may be exhausted", "severity": "high"}],
        overall_confidence="Medium",
    ),
    dict(
        service_event_id=UUIDS["david_lee"],
        evv_checkin_lat=KC_LAT, evv_checkin_lng=KC_LNG,
        evv_checkout_lat=KC_LAT, evv_checkout_lng=KC_LNG,
        evv_caregiver_id="DSP-002",
        diagnosis_code="F70",
        waiver_identifier="Comprehensive",
        duration_minutes=480,
        service_units=32,
        rendering_npi="0987654321",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None, modifier_3=None,
        authorization_number="DSP-AUTH-2026-003",
        flags=[{"flag_type": "auth_expired", "message": "Patient authorization may be expired", "severity": "high"}],
        overall_confidence="Low",
    ),
    dict(
        service_event_id=UUIDS["susan_brown"],
        evv_checkin_lat=KC_LAT, evv_checkin_lng=KC_LNG,
        evv_checkout_lat=KC_LAT, evv_checkout_lng=KC_LNG,
        evv_caregiver_id="DSP-002",
        diagnosis_code="F72",
        waiver_identifier="Comprehensive",
        duration_minutes=480,
        service_units=32,
        rendering_npi="0987654321",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None, modifier_3=None,
        authorization_number="DSP-AUTH-2026-004",
        flags=[{"flag_type": "code_mismatch", "message": "Possible service code mismatch with authorization", "severity": "high"}],
        overall_confidence="Low",
    ),
    dict(
        service_event_id=UUIDS["james_wilson"],
        evv_checkin_lat=KC_LAT, evv_checkin_lng=KC_LNG,
        evv_checkout_lat=KC_LAT, evv_checkout_lng=KC_LNG,
        evv_caregiver_id="DSP-001",
        diagnosis_code="F84",
        waiver_identifier="Partnership for Hope",  # waiver mismatch scenario
        duration_minutes=480,
        service_units=32,
        rendering_npi="1234567890",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None, modifier_3=None,
        authorization_number="DSP-AUTH-2026-005",
        flags=[{"flag_type": "waiver_mismatch", "message": "Waiver type mismatch with authorization", "severity": "high"}],
        overall_confidence="Low",
    ),
    dict(
        service_event_id=UUIDS["linda_martinez"],
        evv_checkin_lat=KC_LAT, evv_checkin_lng=KC_LNG,
        evv_checkout_lat=KC_LAT, evv_checkout_lng=KC_LNG,
        evv_caregiver_id="DSP-001",
        diagnosis_code="F70",
        waiver_identifier="Comprehensive",
        duration_minutes=480,
        service_units=32,
        rendering_npi="1234567890",
        procedure_code="T2016",
        modifier_1="UP",
        modifier_2=None, modifier_3=None,
        authorization_number="DSP-AUTH-2026-006",
        flags=[],
        overall_confidence="High",
    ),
]

MAR_RECORDS = [
    dict(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        service_event_id=UUIDS["john_smith"],
        med_name="Metformin",
        med_dosage="500mg",
        med_time_administered=time(8, 0, 0),
        variance_code=None,
    ),
    dict(
        id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        service_event_id=UUIDS["maria_garcia"],
        med_name="Lisinopril",
        med_dosage="10mg",
        med_time_administered=time(8, 0, 0),
        variance_code=None,
    ),
    dict(
        id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        service_event_id=UUIDS["maria_garcia"],
        med_name="Atorvastatin",
        med_dosage="20mg",
        med_time_administered=time(12, 0, 0),
        variance_code=None,
    ),
    dict(
        id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        service_event_id=UUIDS["susan_brown"],
        med_name="Risperidone",
        med_dosage="1mg",
        med_time_administered=time(8, 0, 0),
        variance_code=None,
    ),
    dict(
        id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        service_event_id=UUIDS["linda_martinez"],
        med_name="Sertraline",
        med_dosage="50mg",
        med_time_administered=time(8, 0, 0),
        variance_code=None,
    ),
    # David Lee and James Wilson have no MAR rows — tests the empty-MAR path
]


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Clear in FK-safe order
        await session.execute(delete(MAR))
        await session.execute(delete(ServiceMetadata))
        await session.execute(delete(ProgressNote))
        await session.flush()

        # Insert using ON CONFLICT DO NOTHING so re-runs are safe
        await session.execute(
            insert(ProgressNote).values(PROGRESS_NOTES).on_conflict_do_nothing()
        )
        await session.execute(
            insert(ServiceMetadata).values(SERVICE_METADATA).on_conflict_do_nothing()
        )
        await session.execute(
            insert(MAR).values(MAR_RECORDS).on_conflict_do_nothing()
        )

        await session.commit()
        print(f"Seeded {len(PROGRESS_NOTES)} patients, {len(MAR_RECORDS)} MAR records.")


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
