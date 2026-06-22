from fastapi import APIRouter, HTTPException
from api.models import AuthorizationRequest, AuthorizationResponse, MockPatient
from api.service import find_authorization, list_all_patients

router = APIRouter()


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
    return list_all_patients()