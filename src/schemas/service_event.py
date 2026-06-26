import uuid
from datetime import date, time

from pydantic import BaseModel

from schemas.auth import AuthorizationDetails


class MARRecord(BaseModel):
    """
    Input: Row from medication_administration_records joined with prescribed_medications.
    Description: A single medication administration record for one shift.
                 variance_code is None when the medication was administered as scheduled.
                 med_time_administered is None when the medication was not given.
    Output: Embedded in EnrichedServiceEvent.mar_records list.
    """
    id: uuid.UUID
    service_event_id: uuid.UUID
    med_name: str
    med_dosage: str
    med_time_administered: time | None    # None when medication was not given
    variance_code: str | None             # reason_if_not_given from medication_administration_records


class EnrichedServiceEvent(BaseModel):
    """
    Input: Joined data from documented_care_sessions + staff_shift_assignments + care_recipients
           + support_plan_goals (for goal text resolution) + medication_administration_records
           + mock Medicaid authorization API response.
    Description: The fully enriched service event produced by Step 1 (Fetch).
                 Contains all fields needed by Step 2 (Validate) and Step 3 (Claim Builder).
    Output: Returned by GET /api/v1/fetch/{service_event_id}. Consumed by Step 2.
    """
    # --- identity (documented_care_sessions.care_session_id) ---
    service_event_id: uuid.UUID

    # --- from care_recipients ---
    participant_name: str
    participant_dcn: str
    participant_dob: date
    sex: str                              # 'M', 'F', or 'U' — 837P DMG03

    # --- from staff_shift_assignments ---
    service_date: date
    service_location: str
    provider_name: str
    procedure_code: str
    rendering_npi: str                    # 837P Loop 2310B NM109
    modifier_1: str                       # 837P SV101-3
    modifier_2: str | None = None         # 837P SV101-4 (optional)
    modifier_3: str | None = None         # 837P SV101-5 (optional)

    # --- from documented_care_sessions ---
    begin_time: time | None = None        # actual_clock_in_time.time() — None if clock-in not recorded
    end_time: time | None = None          # actual_clock_out_time.time() — None if clock-out not recorded
    provider_signature: str               # "signed" / "unsigned" derived from dsp_has_signed boolean
    service_description: str
    activity_time: str | None = None      # derived: "HH:MM-HH:MM" from clock in/out — None if times missing
    participation_level: str
    support_level: str
    goals_supported: list[str]            # resolved from goals_addressed_in_session uuid[] via support_plan_goals
    activity_category: str | None = None  # derived from service_billing_code (e.g. T2016 → "Residential Habilitation")
    health_observations: str | None
    behavioral_notes: str | None
    community_activity: str | None
    meal_type: str | None                 # meals_provided text[] joined to comma-separated string
    personal_care_type: str | None        # personal_care_activities text[] joined to comma-separated string

    # --- EVV from documented_care_sessions ---
    evv_checkin_lat: float | None
    evv_checkin_lng: float | None
    evv_checkout_lat: float | None
    evv_checkout_lng: float | None
    evv_caregiver_id: str | None = None   # not in schema.sql — reserved for future use

    # --- billing metadata ---
    diagnosis_code: str                   # from care_recipients.primary_diagnosis_code
    waiver_identifier: str                # from care_recipients.waiver_program
    duration_minutes: int
    service_units: int
    authorization_number: str | None      # not in schema.sql — reserved for DSP service auth
    flags: list[dict]                     # documentation_gap_flags text[] → list[{"message": str}]
    overall_confidence: str               # ai_confidence_rating (High/Medium/Low)

    # --- from medication_administration_records + prescribed_medications ---
    mar_records: list[MARRecord]

    # --- from mock Medicaid authorization API ---
    authorization: AuthorizationDetails
