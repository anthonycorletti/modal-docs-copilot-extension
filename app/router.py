from fastapi import APIRouter

from app.copilot.router import router as copilot_router
from app.health.router import router as health_router
from app.oauth.router import router as oauth_router

router = APIRouter()

# /health
router.include_router(health_router, tags=["health"])

# /oauth
router.include_router(oauth_router, tags=["oauth"])

# /copilot
router.include_router(copilot_router, tags=["copilot"])
