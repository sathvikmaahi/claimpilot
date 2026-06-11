"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.middleware import RequestContextMiddleware
from api.router import api_router
from core.config import Settings, get_settings
from core.exceptions import AgenticAIError
from core.lifecycle import on_shutdown, on_startup


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    load_dotenv()
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await on_startup(app, resolved_settings)
        yield
        await on_shutdown(app)

    app = FastAPI(
        title=resolved_settings.app_name,
        description="Google ADK multi-agent service",
        version="0.1.0",
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(AgenticAIError)
    async def agentic_ai_error_handler(_request: object, exc: AgenticAIError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": exc.message, "details": exc.details},
        )

    app.include_router(api_router)

    return app
