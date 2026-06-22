import uuid
from datetime import date, time

from pydantic import BaseModel

from schemas.auth import AuthorizationDetails


class MARRecord(BaseModel):
    """
    Input: Row from the Pipeline A mar table.
    Description: A single medication administration record for one shift.
                 variance_code is None when the medication was administered as scheduled.
    Output: Embedded in EnrichedServiceEvent.mar_records list.
    """
    id: uuid.UUID
    service_event_id: uuid.UUID
    med_name: str
    med_dosage: str
    med_time_administered: time
    variance_code: str | None


class EnrichedServiceEvent(BaseModel):
    """
    Input: Merged data from progress_notes, service_metadata, mar tables + mock auth API response.
    Description: The fully enriched service event produced by Step 1 (Fetch).
                 Contains all fields needed by Step 2 (Validate) and Step 3 (Claim Builder).
                 Passes directly to the validation checks without any transformation.
    Output: Returned by GET /api/v1/fetch/{service_event_id}. Consumed by Step 2.
    """
    # --- from progress_notes ---
    service_event_id: uuid.UUID
    participant_name: str
    participant_dcn: str
    participant_dob: date
    service_date: date
    begin_time: time
    end_time: time
    service_location: str
    provider_name: str
    provider_signature: str
    service_description: str
    activity_time: str
    participation_level: str
    support_level: str
    goals_supported: list[str]
    activity_category: str
    health_observations: str | None
    behavioral_notes: str | None
    community_activity: str | None
    meal_type: str | None
    personal_care_type: str | None

    # --- from service_metadata ---
    evv_checkin_lat: float | None
    evv_checkin_lng: float | None
    evv_checkout_lat: float | None
    evv_checkout_lng: float | None
    evv_caregiver_id: str
    diagnosis_code: str
    waiver_identifier: str
    duration_minutes: int
    service_units: int
    rendering_npi: str
    procedure_code: str
    modifier_1: str
    modifier_2: str | None
    modifier_3: str | None
    authorization_number: str | None  # DSP service auth — NOT the patient prior auth
    flags: list[dict]
    overall_confidence: str

    # --- from mar table ---
    mar_records: list[MARRecord]

    # --- from mock Medicaid authorization API ---
    authorization: AuthorizationDetails
