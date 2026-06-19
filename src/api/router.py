from fastapi import APIRouter
from api.routes.health import router as health_router
from api.routes.authorization import router as authorization_router

router = APIRouter()
router.include_router(health_router)
router.include_router(authorization_router)