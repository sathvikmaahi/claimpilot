def test_mock_patients_returns_200(client):
    response = client.get("/mock-patients")
    assert response.status_code == 200


def test_mock_patients_returns_all_seven(client):
    response = client.get("/mock-patients")
    data = response.json()
    assert len(data) == 7


def test_mock_patients_have_required_fields(client):
    response = client.get("/mock-patients")
    for patient in response.json():
        assert "patient_name" in patient
        assert "insurance_number" in patient
        assert "scenario" in patient


def test_mock_patients_contains_known_patient(client):
    response = client.get("/mock-patients")
    names = [p["patient_name"] for p in response.json()]
    assert "John Smith" in names