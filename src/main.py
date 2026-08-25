from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from api.router import router
from api.routes import fetch, validate, claim_builder, clerk_review, process_claims, rejected_claims
from core.logging import setup_logging

from fastapi.middleware.cors import CORSMiddleware
from api.routes import extract, submit, transcribe, roster, extract_image

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    app.state.http_client = httpx.AsyncClient()
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="ClaimPilot AI",
    description="Mock Medicaid Authorization API and Clerk Assistance Pipeline for ClaimPilot AI — Pipeline B POC",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(fetch.router, prefix="/api/v1", tags=["fetch"])
app.include_router(validate.router, prefix="/api/v1", tags=["validate"])
app.include_router(claim_builder.router, prefix="/api/v1", tags=["claim-builder"])
app.include_router(clerk_review.router, prefix="/api/v1", tags=["clerk-review"])
app.include_router(process_claims.router, prefix="/api/v1", tags=["process-claims"])
app.include_router(rejected_claims.router, prefix="/api/v1", tags=["rejected-claims"])


# --- Voice agent (Pipeline A) integration -------------------------------------
# Mounts the voice-note routes and enables browser CORS on the same app, so a
# single `main:app` serves both the clerk (Pipeline B) and voice (Pipeline A)
# pipelines. Added during the voice_agent -> src/ merge.

# CORS — lets a browser frontend (different origin) call this API.
# POC: allow all origins. TIGHTEN before production — restrict allow_origins to
# the actual frontend URL(s), since this is a Medicaid/PHI app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # POC only — replace with frontend origin(s) for prod
    allow_credentials=False,  # must be False while allow_origins is "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extract.router, prefix="/api/v1", tags=["extract"])
app.include_router(submit.router, prefix="/api/v1", tags=["submit"])
app.include_router(transcribe.router, prefix="/api/v1", tags=["transcribe"])
app.include_router(roster.router, prefix="/api/v1", tags=["roster"])
app.include_router(extract_image.router, prefix="/api/v1", tags=["extract-image"])
