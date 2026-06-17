from fastapi import APIRouter, HTTPException
from models import AuthorizationRequest, AuthorizationResponse, MockPatient
from service import find_authorization, list_all_patients

router = APIRouter()


@router.get("/health", status_code=200)
def health_check():
    """
    Input: None.
    Description: Health check endpoint to confirm the service is running.
    Output: 200 — JSON with status "ok" and service name.
    """
    return {"status": "ok", "service": "Mock Medicaid Authorization API"}


@router.post(
    "/authorization",
    response_model=AuthorizationResponse,
    status_code=200,
    responses={
        404: {"description": "No authorization record found for the given patient name and insurance number."},
        422: {"description": "Invalid input — patient_name or insurance_number must not be blank."},
    },
)
def get_authorization(request: AuthorizationRequest):
    """
    Input: AuthorizationRequest — patient_name (str), insurance_number (str).
    Description: Looks up the patient's prior authorization record by name and insurance number.
    Output: 200 — AuthorizationResponse with auth number, authorized units, validity dates, service code, and waiver type.
            404 — No record found for the given patient.
            422 — patient_name or insurance_number is blank.
    """
    result = find_authorization(request.patient_name, request.insurance_number)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No authorization record found for patient '{request.patient_name}' "
                   f"with insurance number '{request.insurance_number}'"
        )

    return result


@router.get(
    "/mock-patients",
    response_model=list[MockPatient],
    status_code=200,
)
def list_mock_patients():
    """
    Input: None.
    Description: Debug endpoint that lists all mock patients and their associated test scenario.
    Output: 200 — List of MockPatient objects with patient_name, insurance_number, and scenario.
    """
    return list_all_patients()
