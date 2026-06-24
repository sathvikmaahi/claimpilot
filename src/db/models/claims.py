import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Numeric, Text, TIMESTAMP, func
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

    file_837p_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clerk_reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clerk_review_timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
