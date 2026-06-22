from collections.abc import AsyncGenerator

import httpx
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, settings
from db.session import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Input: None — called by FastAPI dependency injection.
    Description: Yields an async SQLAlchemy session per request and closes it on teardown.
    Output: AsyncSession bound to the configured PostgreSQL database.
    """
    async with async_session_factory() as session:
        yield session


def get_http_client(request: Request) -> httpx.AsyncClient:
    """
    Input: FastAPI Request — carries app.state populated during lifespan startup.
    Description: Returns the shared httpx.AsyncClient created at app startup.
                 The client is reused across requests to benefit from connection pooling.
    Output: httpx.AsyncClient instance.
    """
    return request.app.state.http_client


def get_settings() -> Settings:
    """
    Input: None.
    Description: Returns the application settings singleton loaded from environment / .env file.
                 Can be overridden in tests via app.dependency_overrides.
    Output: Settings instance.
    """
    return settings
