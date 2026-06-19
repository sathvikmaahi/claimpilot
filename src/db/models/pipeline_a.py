import uuid
from datetime import date, time

from sqlalchemy import ForeignKey, String, Text, Date, Time, Integer, Float, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class ProgressNote(Base):
    """
    Pipeline A progress_notes table — the DSP's confirmed shift record.
    Read-only from Pipeline B's perspective. One row per ISL shift.
    """
    __tablename__ = "progress_notes"

    service_event_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_name: Mapped[str] = mapped_column(String(255))
    participant_dcn: Mapped[str] = mapped_column(String(50))  # Missouri Medicaid 9-digit ID, used as insurance_number for auth API
    participant_dob: Mapped[date] = mapped_column(Date)
    service_date: Mapped[date] = mapped_column(Date)
    begin_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    service_location: Mapped[str] = mapped_column(String(255))
    provider_name: Mapped[str] = mapped_column(String(255))
    provider_signature: Mapped[str] = mapped_column(String(255))
    service_description: Mapped[str] = mapped_column(Text)
    activity_time: Mapped[str] = mapped_column(String(100))
    participation_level: Mapped[str] = mapped_column(String(255))
    support_level: Mapped[str] = mapped_column(String(100))
    goals_supported: Mapped[list] = mapped_column(JSONB)
    activity_category: Mapped[str] = mapped_column(String(100))
    health_observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    behavioral_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    community_activity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meal_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    personal_care_type: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MAR(Base):
    """
    Pipeline A mar table — medication administration records for each shift.
    One row per medication administered. May be empty for a given shift.
    """
    __tablename__ = "mar"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("progress_notes.service_event_id"),
    )
    med_name: Mapped[str] = mapped_column(String(255))
    med_dosage: Mapped[str] = mapped_column(String(100))
    med_time_administered: Mapped[time] = mapped_column(Time)
    variance_code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ServiceMetadata(Base):
    """
    Pipeline A service_metadata table — EVV, billing codes, modifiers, and AI-computed fields.
    One row per service event. service_event_id is both PK and FK.
    """
    __tablename__ = "service_metadata"

    service_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("progress_notes.service_event_id"),
        primary_key=True,
    )
    evv_checkin_lat: Mapped[float] = mapped_column(Float)
    evv_checkin_lng: Mapped[float] = mapped_column(Float)
    evv_checkout_lat: Mapped[float] = mapped_column(Float)
    evv_checkout_lng: Mapped[float] = mapped_column(Float)
    evv_caregiver_id: Mapped[str] = mapped_column(String(100))
    diagnosis_code: Mapped[str] = mapped_column(String(20))
    waiver_identifier: Mapped[str] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    service_units: Mapped[int] = mapped_column(Integer)
    rendering_npi: Mapped[str] = mapped_column(String(10))
    procedure_code: Mapped[str] = mapped_column(String(10))
    modifier_1: Mapped[str] = mapped_column(String(10))
    modifier_2: Mapped[str | None] = mapped_column(String(10), nullable=True)
    modifier_3: Mapped[str | None] = mapped_column(String(10), nullable=True)
    authorization_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    flags: Mapped[list] = mapped_column(JSONB)
    overall_confidence: Mapped[str] = mapped_column(String(20))
