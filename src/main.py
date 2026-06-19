from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI

from api.router import router
from api.routes import fetch, validate, claim_builder, clerk_review
from core.logging import setup_logging


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
