from fastapi import FastAPI
from routes import router

app = FastAPI(
    title="Mock Medicaid Authorization API",
    description="Simulates MO HealthNet authorization API for ClaimPilot AI — Pipeline B POC",
    version="1.0.0"
)

app.include_router(router)
