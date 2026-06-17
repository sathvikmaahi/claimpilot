from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import date

app = FastAPI(
    title="Mock Medicaid Authorization API",
    description="Simulates MO HealthNet authorization API for ClaimPilot AI — Pipeline B POC",
    version="1.0.0"
)

# ---------------------------------------------------------------------------
# Mock authorization data store
# Covers 6 scenarios for validation testing
# ---------------------------------------------------------------------------

MOCK_AUTHORIZATIONS = {
    ("John Smith", "MO100001"): {
        "patient_prior_auth_number": "AUTH-2026-00101",
        "authorized_units": 96,
        "validity_start_date": "2026-01-01",
        "validity_end_date": "2026-12-31",
        "authorized_service_code": "T2016",
        "waiver_type": "Comprehensive",
        "_scenario": "Valid auth — clean pass"
    },
    ("Maria Garcia", "MO100002"): {
        "patient_prior_auth_number": "AUTH-2026-00102",
        "authorized_units": 0,                          # Units exhausted
        "validity_start_date": "2026-01-01",
        "validity_end_date": "2026-12-31",
        "authorized_service_code": "T2016",
        "waiver_type": "Comprehensive",
        "_scenario": "CO-151 fail — units exhausted"
    },
    ("David Lee", "MO100003"): {
        "patient_prior_auth_number": "AUTH-2025-00103",
        "authorized_units": 48,
        "validity_start_date": "2025-01-01",
        "validity_end_date": "2025-12-31",              # Expired
        "authorized_service_code": "T2016",
        "waiver_type": "Comprehensive",
        "_scenario": "Check 1 fail — expired auth"
    },
    ("Susan Brown", "MO100004"): {
        "patient_prior_auth_number": "AUTH-2026-00104",
        "authorized_units": 64,
        "validity_start_date": "2026-01-01",
        "validity_end_date": "2026-12-31",
        "authorized_service_code": "T2021",             # Wrong service code
        "waiver_type": "Comprehensive",
        "_scenario": "Check 2 fail — service code mismatch"
    },
    ("James Wilson", "MO100005"): {
        "patient_prior_auth_number": "AUTH-2026-00105",
        "authorized_units": 80,
        "validity_start_date": "2026-01-01",
        "validity_end_date": "2026-12-31",
        "authorized_service_code": "T2016",
        "waiver_type": "Partnership for Hope",          # Wrong waiver
        "_scenario": "Check 3 fail — waiver type mismatch"
    },
    ("Linda Martinez", "MO100006"): {
        "patient_prior_auth_number": "AUTH-2026-00106",
        "authorized_units": 120,
        "validity_start_date": "2026-01-01",
        "validity_end_date": "2026-12-31",
        "authorized_service_code": "T2016",
        "waiver_type": "Comprehensive",
        "_scenario": "Valid auth — clean pass (second patient)"
    },
}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AuthorizationRequest(BaseModel):
    patient_name: str
    insurance_number: str

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

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Mock Medicaid Authorization API"}


@app.post("/authorization", response_model=AuthorizationResponse)
def get_authorization(request: AuthorizationRequest):
    """
    Look up patient authorization by name + insurance number.
    Returns prior auth details for Pipeline B validation and claim building.
    """
    key = (request.patient_name.strip(), request.insurance_number.strip())
    record = MOCK_AUTHORIZATIONS.get(key)

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No authorization record found for patient '{request.patient_name}' "
                   f"with insurance number '{request.insurance_number}'"
        )

    return AuthorizationResponse(
        patient_prior_auth_number=record["patient_prior_auth_number"],
        authorized_units=record["authorized_units"],
        validity_start_date=record["validity_start_date"],
        validity_end_date=record["validity_end_date"],
        authorized_service_code=record["authorized_service_code"],
        waiver_type=record["waiver_type"],
    )


@app.get("/mock-patients", response_model=list[MockPatient])
def list_mock_patients():
    """
    Debug endpoint — lists all mock patients and their test scenario.
    For development use only.
    """
    return [
        MockPatient(
            patient_name=name,
            insurance_number=ins_num,
            scenario=record["_scenario"]
        )
        for (name, ins_num), record in MOCK_AUTHORIZATIONS.items()
    ]
