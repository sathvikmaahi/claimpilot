import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, String, Numeric, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Claim(Base):
    """
    Pipeline B claims table — tracks each claim from validation through clerk confirmation.

    claim_status lifecycle:
      failed       → validation failed; claim sits in review queue
      validated    → all 5 checks passed; ready for Step 3 Claim Builder
      draft        → Step 3 is building the 837P EDI file
      clerk_reviewed → clerk has reviewed but not yet confirmed
      confirmed    → clerk confirmed; final 837P produced; end of Pipeline B

    Billing fields (billing_npi, payer_id, billed_amount) are NULL until Step 3 populates them.
    Failure fields (validation_failure_check, validation_failure_reason) are NULL for passing claims.
    """
    __tablename__ = "claims"

    claim_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documented_care_sessions.care_session_id"),
    )
    patient_auth_number: Mapped[str] = mapped_column(String(100))          # REF G1 on 837P — from mock auth API

    # Populated at Step 3 (Claim Builder) — NULL for failed claims in review queue
    billing_npi: Mapped[str | None] = mapped_column(String(10), nullable=True)           # Life Unlimited org NPI
    payer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)             # MO HealthNet payer ID
    billed_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True) # Life Unlimited T2016 fee schedule

    claim_status: Mapped[str] = mapped_column(String(50))                  # See lifecycle above

    # NULL for passing claims — populated when validation fails
    validation_failure_check: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    file_837p_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    clerk_reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clerk_review_timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class ClaimFieldsRecord(Base):
    """
    Pipeline B claim_fields table — structured 837P fields produced by the Claim Builder agent.
    One-to-one with claims (same claim_id). Stored separately so Step 4 (Clerk Review) can
    read and edit individual fields without parsing the raw EDI text.
    """
    __tablename__ = "claim_fields"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("claims.claim_id"),
        primary_key=True,
    )

    # Loop 2000B — Subscriber
    subscriber_last_name: Mapped[str] = mapped_column(Text)
    subscriber_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscriber_medicaid_id: Mapped[str] = mapped_column(Text)
    subscriber_dob: Mapped[str] = mapped_column(String(8))         # YYYYMMDD
    subscriber_sex: Mapped[str] = mapped_column(String(1))

    # Loop 2300 — Claim
    service_date: Mapped[str] = mapped_column(String(8))           # YYYYMMDD
    service_begin_time: Mapped[str | None] = mapped_column(String(4), nullable=True)  # HHMM
    service_end_time: Mapped[str | None] = mapped_column(String(4), nullable=True)
    diagnosis_code: Mapped[str] = mapped_column(Text)
    waiver_type: Mapped[str] = mapped_column(String(100))
    diagnosis_qualifier: Mapped[str] = mapped_column(String(3))
    place_of_service: Mapped[str] = mapped_column(String(2))
    claim_filing_indicator: Mapped[str] = mapped_column(String(2))

    # Loop 2310B — Rendering Provider
    rendering_npi: Mapped[str] = mapped_column(String(10))

    # Loop 2400 — Service Line
    procedure_code: Mapped[str] = mapped_column(String(10))
    procedure_qualifier: Mapped[str] = mapped_column(String(2))
    modifier_1: Mapped[str] = mapped_column(String(10))
    modifier_2: Mapped[str | None] = mapped_column(String(10), nullable=True)
    modifier_3: Mapped[str | None] = mapped_column(String(10), nullable=True)
    service_units: Mapped[int] = mapped_column(Integer)
    billed_amount: Mapped[str] = mapped_column(String(12))         # "0.00" string as agent produced
    taxonomy_code: Mapped[str] = mapped_column(String(10))

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
