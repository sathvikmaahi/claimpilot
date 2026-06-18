import pytest


VALID_PATIENTS = [
    ("John Smith", "MO100001", "AUTH-2026-00101", 96, "T2016", "Comprehensive"),
    ("Maria Garcia", "MO100002", "AUTH-2026-00102", 0, "T2016", "Comprehensive"),
    ("David Lee", "MO100003", "AUTH-2025-00103", 48, "T2016", "Comprehensive"),
    ("Susan Brown", "MO100004", "AUTH-2026-00104", 64, "T2021", "Comprehensive"),
    ("James Wilson", "MO100005", "AUTH-2026-00105", 80, "T2016", "Partnership for Hope"),
    ("Linda Martinez", "MO100006", "AUTH-2026-00106", 120, "T2016", "Comprehensive"),
]


@pytest.mark.parametrize("name,ins_num,auth_num,units,service_code,waiver", VALID_PATIENTS)
def test_valid_authorization_returns_200(client, name, ins_num, auth_num, units, service_code, waiver):
    response = client.post("/authorization", json={"patient_name": name, "insurance_number": ins_num})
    assert response.status_code == 200
    data = response.json()
    assert data["patient_prior_auth_number"] == auth_num
    assert data["authorized_units"] == units
    assert data["authorized_service_code"] == service_code
    assert data["waiver_type"] == waiver


def test_unknown_patient_returns_404(client):
    response = client.post("/authorization", json={"patient_name": "Unknown Patient", "insurance_number": "MO999999"})
    assert response.status_code == 404
    assert "No authorization record found" in response.json()["detail"]


def test_blank_patient_name_returns_422(client):
    response = client.post("/authorization", json={"patient_name": "", "insurance_number": "MO100001"})
    assert response.status_code == 422


def test_blank_insurance_number_returns_422(client):
    response = client.post("/authorization", json={"patient_name": "John Smith", "insurance_number": ""})
    assert response.status_code == 422


def test_whitespace_only_patient_name_returns_422(client):
    response = client.post("/authorization", json={"patient_name": "   ", "insurance_number": "MO100001"})
    assert response.status_code == 422


def test_missing_fields_returns_422(client):
    response = client.post("/authorization", json={})
    assert response.status_code == 422