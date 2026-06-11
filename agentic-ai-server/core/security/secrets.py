"""Cloud Run-safe secret resolution."""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)


def resolve_secret(env_var: str, *, required: bool = False) -> str:
    """Resolve a secret from environment (injected by Secret Manager on Cloud Run)."""
    value = os.environ.get(env_var, "")
    if required and not value:
        logger.error("required_secret_missing", env_var=env_var)
        raise RuntimeError(f"Required secret '{env_var}' is not configured")
    return value


def load_runtime_secrets() -> dict[str, bool]:
    """Validate expected secret env vars without logging values."""
    checks = {
        "google_api_key": bool(os.environ.get("GOOGLE_API_KEY")),
        "google_cloud_project": bool(os.environ.get("GOOGLE_CLOUD_PROJECT")),
    }
    logger.info("runtime_secrets_checked", configured={k: v for k, v in checks.items()})
    return checks
