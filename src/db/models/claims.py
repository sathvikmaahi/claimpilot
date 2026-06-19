import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, String, Numeric, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Claim(Base):
    """
    Pipeline B claims table — written by Pipeline B after clerk confirmation.
    Tracks each claim from draft through clerk-confirmed status.
    claim_status lifecycle: draft → validated → clerk_reviewed → confirmed
    """
    __tablename__ = "claims"

    claim_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("progress_notes.service_event_id"),
    )
    patient_auth_number: Mapped[str] = mapped_column(String(100))   # REF G1 on 837P — from mock auth API
    billing_npi: Mapped[str] = mapped_column(String(10))            # Life Unlimited org NPI
    payer_id: Mapped[str] = mapped_column(String(100))              # MO HealthNet payer ID
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # From Life Unlimited T2016 fee schedule
    claim_status: Mapped[str] = mapped_column(String(50))
    file_837p_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clerk_reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clerk_review_timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
