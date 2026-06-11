"""Application entry point for local development and container deployment."""

from __future__ import annotations

import os

import uvicorn

from app.factory import create_app
from core.config import get_settings

app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=int(os.environ.get("PORT", settings.port)),
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
        factory=False,
    )


if __name__ == "__main__":
    run()
