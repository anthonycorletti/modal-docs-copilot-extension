import structlog
from fastapi import APIRouter, Request

from app.oauth.schemas import OauthCallbackResponse

router = APIRouter()
log = structlog.get_logger()


class Routes:
    oauth_callback = "/oauth/callback"


@router.get(Routes.oauth_callback, response_model=OauthCallbackResponse)
async def oauth_callback(request: Request) -> OauthCallbackResponse:
    log.info("Received OAuth callback request", request=request)
    return OauthCallbackResponse(message="ok!")
