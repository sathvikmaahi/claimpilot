import uuid
from datetime import date, time, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, Time, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class CareRecipient(Base):
    """
    Pipeline A care_recipients table — one row per individual served.
    Provides participant_name (full_name), participant_dcn (medicaid_id),
    participant_dob, diagnosis_code, waiver_identifier, and sex.
    Read-only from Pipeline B's perspective.
    """
    __tablename__ = "care_recipients"

    care_recipient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    full_name: Mapped[str] = mapped_column(Text)                    # → participant_name
    medicaid_id: Mapped[str] = mapped_column(String(50))            # → participant_dcn (MO 9-digit Medicaid ID)
    date_of_birth: Mapped[date] = mapped_column(Date)               # → participant_dob
    waiver_program: Mapped[str] = mapped_column(Text)               # → waiver_identifier
    primary_diagnosis_code: Mapped[str] = mapped_column(Text)       # → diagnosis_code (ICD-10)
    sex: Mapped[str] = mapped_column(String(1))  # → sex ('M', 'F', 'U') — 837P DMG03
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class ServiceLocation(Base):
    """
    Pipeline A service_locations table — one row per residential/day programme site.
    Holds the rendering NPI and modifiers used for 837P billing.
    Linked to StaffShiftAssignment via location_id FK.
    """
    __tablename__ = "service_locations"

    location_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    service_location_name: Mapped[str] = mapped_column(Text)              # → service_location
    rendering_npi: Mapped[str] = mapped_column(String(10))                # → 837P Loop 2310B NM109
    modifier_1: Mapped[str] = mapped_column(String(10))                   # → 837P SV101-3
    modifier_2: Mapped[str | None] = mapped_column(String(10), nullable=True)   # → SV101-4
    modifier_3: Mapped[str | None] = mapped_column(String(10), nullable=True)   # → SV101-5
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class StaffShiftAssignment(Base):
    """
    Pipeline A staff_shift_assignments table — one row per scheduled DSP shift.
    Provides service_date, provider_name, procedure_code.
    rendering_npi, modifiers, and service_location_name come from ServiceLocation via location_id.
    """
    __tablename__ = "staff_shift_assignments"

    shift_assignment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    care_recipient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("care_recipients.care_recipient_id")
    )
    direct_support_professional_name: Mapped[str] = mapped_column(Text)   # → provider_name
    location_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("service_locations.location_id")
    )
    shift_date: Mapped[date] = mapped_column(Date)                        # → service_date
    scheduled_start_time: Mapped[time] = mapped_column(Time)
    scheduled_end_time: Mapped[time] = mapped_column(Time)
    service_billing_code: Mapped[str] = mapped_column(String(10))         # → procedure_code
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class DocumentedCareSession(Base):
    """
    Pipeline A documented_care_sessions table — the DSP's confirmed shift record.
    Primary entity for Pipeline B Step 1 (Fetch). care_session_id is used as service_event_id
    throughout Pipeline B — it is what is passed to GET /api/v1/fetch/{service_event_id}.
    Replaces the old flat progress_notes + service_metadata tables.
    """
    __tablename__ = "documented_care_sessions"

    care_session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shift_assignment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_shift_assignments.shift_assignment_id")
    )
    care_recipient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("care_recipients.care_recipient_id")
    )
    actual_clock_in_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)   # → begin_time (.time() extracted)
    actual_clock_out_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)  # → end_time (.time() extracted)
    total_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)         # → duration_minutes
    billable_units_calculated: Mapped[int | None] = mapped_column(Integer, nullable=True)      # → service_units
    care_session_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)            # → service_description
    activities_performed: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    level_of_support_provided: Mapped[str | None] = mapped_column(Text, nullable=True)         # → support_level (verbal_prompts/physical_assistance/full_support/independent)
    recipient_engagement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)        # → participation_level
    health_observations_notes: Mapped[str | None] = mapped_column(Text, nullable=True)         # → health_observations
    behavioral_observations_notes: Mapped[str | None] = mapped_column(Text, nullable=True)     # → behavioral_notes
    community_outing_notes: Mapped[str | None] = mapped_column(Text, nullable=True)            # → community_activity
    meals_provided: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)            # → meal_type (joined to comma string)
    personal_care_activities: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)  # → personal_care_type (joined to comma string)
    goals_addressed_in_session: Mapped[list | None] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=True)  # UUIDs → resolved to text via support_plan_goals
    checkin_location_latitude: Mapped[float | None] = mapped_column(nullable=True)             # → evv_checkin_lat
    checkin_location_longitude: Mapped[float | None] = mapped_column(nullable=True)            # → evv_checkin_lng
    checkout_location_latitude: Mapped[float | None] = mapped_column(nullable=True)            # → evv_checkout_lat
    checkout_location_longitude: Mapped[float | None] = mapped_column(nullable=True)           # → evv_checkout_lng
    ai_confidence_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)        # → overall_confidence (High/Medium/Low)
    documentation_gap_flags: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)   # → flags (text[] → list[dict])
    dsp_has_signed: Mapped[bool] = mapped_column(Boolean, default=False)                       # → provider_signature ("signed"/"unsigned")
    session_status: Mapped[str] = mapped_column(String(50), default="in_progress")
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    record_updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    goals_resolution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PrescribedMedication(Base):
    """
    Pipeline A prescribed_medications table — medication profile per participant.
    Joined to MedicationAdministrationRecord to resolve med_name and med_dosage for the MAR.
    """
    __tablename__ = "prescribed_medications"

    medication_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    care_recipient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("care_recipients.care_recipient_id")
    )
    medication_name: Mapped[str] = mapped_column(Text)    # → med_name
    dosage_amount: Mapped[str] = mapped_column(Text)      # → med_dosage
    administration_route: Mapped[str] = mapped_column(Text)
    scheduled_time_of_day: Mapped[time] = mapped_column(Time)
    is_currently_active: Mapped[bool] = mapped_column(Boolean, default=True)
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class MedicationAdministrationRecord(Base):
    """
    Pipeline A medication_administration_records table — one row per medication per shift.
    Joined with PrescribedMedication to resolve med_name and med_dosage.
    was_medication_given + reason_if_not_given replace the old single variance_code field:
      given=True  → variance_code=None
      given=False → variance_code=reason_if_not_given
    """
    __tablename__ = "medication_administration_records"

    administration_record_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    care_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documented_care_sessions.care_session_id")
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("prescribed_medications.medication_id")
    )
    was_medication_given: Mapped[bool] = mapped_column(Boolean)
    actual_administration_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)  # → med_time_administered (.time() extracted)
    reason_if_not_given: Mapped[str | None] = mapped_column(Text, nullable=True)  # → variance_code when not given
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class SupportPlanGoal(Base):
    """
    Pipeline A support_plan_goals table — ISP goals per participant.
    Queried by the fetch service to resolve goals_addressed_in_session (uuid[]) →
    goal_description (str) so the Claim Builder agent receives readable text.
    """
    __tablename__ = "support_plan_goals"

    goal_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    care_recipient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("care_recipients.care_recipient_id")
    )
    goal_category: Mapped[str] = mapped_column(Text)         # daily_living / community_integration / health_and_safety / employment / social_skills
    goal_description: Mapped[str] = mapped_column(Text)      # → goals_supported list item
    is_currently_active: Mapped[bool] = mapped_column(Boolean, default=True)
    record_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
