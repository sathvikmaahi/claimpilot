import json
from pathlib import Path
from api.models import AuthorizationResponse, MockPatient

_DATA_PATH = Path(__file__).parent / "data.json"


def _load_data() -> list[dict]:
    with open(_DATA_PATH) as f:
        return json.load(f)


def find_authorization(patient_name: str, insurance_number: str) -> AuthorizationResponse | None:
    for record in _load_data():
        if record["patient_name"] == patient_name and record["insurance_number"] == insurance_number:
            return AuthorizationResponse(
                patient_prior_auth_number=record["patient_prior_auth_number"],
                authorized_units=record["authorized_units"],
                validity_start_date=record["validity_start_date"],
                validity_end_date=record["validity_end_date"],
                authorized_service_code=record["authorized_service_code"],
                waiver_type=record["waiver_type"],
            )
    return None


def list_all_patients() -> list[MockPatient]:
    return [
        MockPatient(
            patient_name=r["patient_name"],
            insurance_number=r["insurance_number"],
            scenario=r["_scenario"],
        )
        for r in _load_data()
    ]