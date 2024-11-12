from pydantic import BaseModel


class OauthCallbackResponse(BaseModel):
    message: str
