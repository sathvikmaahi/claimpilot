from data import MOCK_AUTHORIZATIONS
from models import AuthorizationResponse, MockPatient


def find_authorization(patient_name: str, insurance_number: str) -> AuthorizationResponse | None:
    """
    Input: patient_name (str), insurance_number (str).
    Description: Looks up a patient's prior authorization record from the mock data store.
    Output: AuthorizationResponse if found, None otherwise.
    """
    key = (patient_name, insurance_number)
    record = MOCK_AUTHORIZATIONS.get(key)

    if not record:
        return None

    return AuthorizationResponse(
        patient_prior_auth_number=record["patient_prior_auth_number"],
        authorized_units=record["authorized_units"],
        validity_start_date=record["validity_start_date"],
        validity_end_date=record["validity_end_date"],
        authorized_service_code=record["authorized_service_code"],
        waiver_type=record["waiver_type"],
    )


def list_all_patients() -> list[MockPatient]:
    """
    Input: None.
    Description: Retrieves all mock patients and their test scenarios from the data store.
    Output: List of MockPatient objects.
    """
    return [
        MockPatient(
            patient_name=name,
            insurance_number=ins_num,
            scenario=record["_scenario"]
        )
        for (name, ins_num), record in MOCK_AUTHORIZATIONS.items()
    ]
