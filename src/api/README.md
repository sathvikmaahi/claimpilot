# Mock Medicaid Authorization API

Simulates MO HealthNet authorization API for ClaimPilot AI — Pipeline B POC.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/authorization` | Look up patient prior authorization |
| GET | `/mock-patients` | List all mock patients and test scenarios |

## Running

From the `src/` directory:

```bash
uvicorn main:app --reload
```

## Request Example

```json
POST /authorization
{
  "patient_name": "John Smith",
  "insurance_number": "MO100001"
}
```