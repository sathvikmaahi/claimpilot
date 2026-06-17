# Mock Medicaid Authorization API

Simulates MO HealthNet authorization API for ClaimPilot AI — Pipeline B POC.

## Setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/authorization` | Main auth lookup |
| `GET` | `/mock-patients` | List all mock patients (debug) |

## Example Request

```bash
curl -X POST http://localhost:8000/authorization \
  -H "Content-Type: application/json" \
  -d '{"patient_name": "John Smith", "insurance_number": "MO100001"}'
```

## Example Response

```json
{
  "patient_prior_auth_number": "AUTH-2026-00101",
  "authorized_units": 96,
  "validity_start_date": "2026-01-01",
  "validity_end_date": "2026-12-31",
  "authorized_service_code": "T2016",
  "waiver_type": "Comprehensive"
}
```

## Mock Patients & Test Scenarios

| Patient | Insurance # | Scenario |
|---|---|---|
| John Smith | MO100001 | Valid auth — clean pass |
| Maria Garcia | MO100002 | CO-151 fail — units exhausted |
| David Lee | MO100003 | Check 1 fail — expired auth |
| Susan Brown | MO100004 | Check 2 fail — service code mismatch |
| James Wilson | MO100005 | Check 3 fail — waiver type mismatch |
| Linda Martinez | MO100006 | Valid auth — clean pass (second patient) |

## Interactive Docs

Once running, visit `http://localhost:8000/docs` for the full Swagger UI.
