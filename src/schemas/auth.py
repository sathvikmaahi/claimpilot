from datetime import date
from pydantic import BaseModel


class AuthorizationRequest(BaseModel):
    """
    Input: patient_name (str), insurance_number (str).
    Description: Request body sent to the mock Medicaid authorization API POST /authorization.
                 insurance_number maps to participant_dcn from the progress_notes table.
    Output: Used as the JSON body of the auth API POST request.
    """
    patient_name: str
    insurance_number: str


class AuthorizationDetails(BaseModel):
    """
    Input: JSON response from mock Medicaid authorization API.
    Description: Prior authorization details returned by the auth API for a given patient.
                 patient_prior_auth_number goes on the 837P as REF G1.
    Output: Embedded in EnrichedServiceEvent.authorization field.
    """
    patient_prior_auth_number: str
    authorized_units: int
    validity_start_date: date
    validity_end_date: date
    authorized_service_code: str
    waiver_type: str
