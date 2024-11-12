import os
from enum import Enum

import structlog
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

log = structlog.get_logger()


class Environment(str, Enum):
    test = "test"
    local = "local"
    preview = "preview"
    production = "production"


environment = Environment(os.getenv("APP_ENV", Environment.local.value))
environment_file = f".env.{environment.value}"


class Settings(BaseSettings):
    ENV: Environment = Environment.local
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    OPENAI_API_KEY: SecretStr = SecretStr("")
    APP_URL: str = "http://127.0.0.1:8000"
    GH_COPILOT_URL: str = "https://api.githubcopilot.com"
    MODAL_CONTENT_PATH: str = "tmp/local/modal-docs.txt"

    model_config = SettingsConfigDict(
        env_prefix="app_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_file=environment_file,
        extra="allow",
    )

    def is_environment(self, environment: Environment) -> bool:
        return self.ENV == environment

    def is_test(self) -> bool:
        return self.is_environment(Environment.test)

    def is_local(self) -> bool:
        return self.is_environment(Environment.local)

    def is_preview(self) -> bool:
        return self.is_environment(Environment.preview)

    def is_production(self) -> bool:
        return self.is_environment(Environment.production)


settings = Settings()

# try to make os.dirname for MODAL_CONTENT_PATH
try:
    if not os.path.exists(os.path.dirname(settings.MODAL_CONTENT_PATH)):
        os.makedirs(os.path.dirname(settings.MODAL_CONTENT_PATH))
except Exception as e:
    log.error(f"Error creating directory: {e}")
