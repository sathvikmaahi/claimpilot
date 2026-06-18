"""FastAPI entrypoint for the ClaimPilot voice agent.

Assembles the app and wires in the route modules. All real work lives in
pipeline.py; the routes are thin HTTP adapters over it. Run locally with:

    uvicorn app:app --reload
"""

from dotenv import load_dotenv
load_dotenv("section_1_agent/.env")  # load DB + Vertex creds before routes import

from fastapi import FastAPI
from api.routes import extract, submit

app = FastAPI(title="ClaimPilot Voice Agent", version="0.1.0")
app.include_router(extract.router)
app.include_router(submit.router)

@app.get("/health")
def health_check():
    """Liveness probe — Cloud Run and you can hit this to confirm the app is up."""
    return {"status": "ok"}