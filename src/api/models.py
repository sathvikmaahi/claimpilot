from pydantic import BaseModel, field_validator
from datetime import date


class AuthorizationRequest(BaseModel):
    patient_name: str
    insurance_number: str

    @field_validator("patient_name", "insurance_number")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class AuthorizationResponse(BaseModel):
    patient_prior_auth_number: str
    authorized_units: int
    validity_start_date: date
    validity_end_date: date
    authorized_service_code: str
    waiver_type: str


class MockPatient(BaseModel):
    patient_name: str
    insurance_number: str
    scenario: str
