"""Async SQLAlchemy engine factory for multiple database roles."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db.config import DatabaseConfig, DatabaseRole, MultiDatabaseSettings

logger = structlog.get_logger(__name__)

_engines: dict[DatabaseRole, AsyncEngine] = {}
_session_factories: dict[DatabaseRole, async_sessionmaker[AsyncSession]] = {}


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///") and "+aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def create_engine_for_role(role: DatabaseRole, config: DatabaseConfig) -> AsyncEngine | None:
    if not config.is_configured or not config.enabled:
        return None

    url = _normalize_url(config.url)
    engine = create_async_engine(
        url,
        echo=config.echo,
        pool_size=config.pool_size if "sqlite" not in url else 0,
    )
    _engines[role] = engine
    _session_factories[role] = async_sessionmaker(engine, expire_on_commit=False)

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception:
        logger.debug("sqlalchemy_otel_instrumentation_skipped", role=role.value)

    logger.info("database_engine_initialized", role=role.value)
    return engine


def initialize_engines(settings: MultiDatabaseSettings) -> dict[DatabaseRole, AsyncEngine | None]:
    return {
        DatabaseRole.APP: create_engine_for_role(DatabaseRole.APP, settings.app),
        DatabaseRole.TELEMETRY: create_engine_for_role(DatabaseRole.TELEMETRY, settings.telemetry),
        DatabaseRole.ANALYTICS: create_engine_for_role(DatabaseRole.ANALYTICS, settings.analytics),
    }


def get_engine(role: DatabaseRole) -> AsyncEngine | None:
    return _engines.get(role)


@asynccontextmanager
async def get_session(role: DatabaseRole) -> AsyncIterator[AsyncSession]:
    factory = _session_factories.get(role)
    if factory is None:
        raise RuntimeError(f"Database role '{role.value}' is not configured")
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_database(role: DatabaseRole) -> str:
    engine = get_engine(role)
    if engine is None:
        return "skipped"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("database_health_check_failed", role=role.value, error=str(exc))
        return "error"


async def shutdown_engines() -> None:
    for role, engine in list(_engines.items()):
        await engine.dispose()
        logger.info("database_engine_disposed", role=role.value)
    _engines.clear()
    _session_factories.clear()
