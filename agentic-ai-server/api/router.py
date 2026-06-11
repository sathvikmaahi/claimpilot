"""Aggregate API router."""

from fastapi import APIRouter

from api.routes import agents, health, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sessions.router)
api_router.include_router(agents.router)
