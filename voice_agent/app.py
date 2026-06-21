"""FastAPI entrypoint for the ClaimPilot voice agent.

Assembles the app and wires in the route modules. All real work lives in
pipeline.py; the routes are thin HTTP adapters over it. Run locally with:

    uvicorn app:app --reload
"""

from dotenv import load_dotenv
load_dotenv("section_1_agent/.env")  # load DB + Vertex creds before routes import

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import extract, submit, transcribe

app = FastAPI(title="ClaimPilot Voice Agent", version="0.1.0")

# CORS — lets a browser frontend (different origin) call this API.
# POC: allow all origins. TIGHTEN before production — restrict allow_origins
# to the actual frontend URL(s), since this is a Medicaid/PHI app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # POC only — replace with frontend origin(s) for prod
    allow_credentials=False,      # must be False while allow_origins is "*"
    allow_methods=["*"],          # GET, POST, OPTIONS, etc.
    allow_headers=["*"],
)
app.include_router(extract.router)
app.include_router(submit.router)
app.include_router(transcribe.router)

@app.get("/health")
def health_check():
    """Liveness probe — Cloud Run and you can hit this to confirm the app is up."""
    return {"status": "ok"}