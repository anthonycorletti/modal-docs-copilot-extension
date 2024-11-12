import json
from typing import Dict

from fastapi import FastAPI
from modal import App, Cron, Image, Secret, Volume, asgi_app
from pydantic import SecretStr
from pydantic_settings import BaseSettings

from app.settings import settings

name = "modal-docs-copilot-extension"
app = App(name=name)
vol = Volume.from_name(label=f"{name}-data", create_if_missing=True)


def _set_app_env_val(settings: BaseSettings, k: str, v: str) -> str | None:
    if isinstance(getattr(settings, k), SecretStr):
        return getattr(settings, k).get_secret_value()
    if isinstance(getattr(settings, k), bool):
        return "true" if getattr(settings, k) else "false"
    return v


_app_env_dict: Dict[str, str | None] = {
    f"APP_{str(k)}": _set_app_env_val(settings, k, v)
    for k, v in json.loads(settings.model_dump_json()).items()
}

app_env = Secret.from_dict(_app_env_dict)

image = (
    Image.debian_slim()
    .pip_install("uv")
    .workdir("/root")
    .copy_local_file("pyproject.toml", "/root/pyproject.toml")
    .copy_local_file("uv.lock", "/root/uv.lock")
    .env({"UV_PROJECT_ENVIRONMENT": "/usr/local"})
    .run_commands(
        [
            "uv sync --frozen --compile-bytecode",
            "uv build",
        ]
    )
)


@app.function(
    image=image,
    secrets=[app_env],
    volumes={"/root/data": vol},
)
@asgi_app(label=f"{name}-api")
def api() -> FastAPI:
    from app.main import app

    return app


@app.function(
    image=image,
    schedule=Cron("0 0 * * *"),
    secrets=[app_env],
    volumes={"/root/data": vol},
)
def run_data_pipeline() -> None:
    from app.copilot.service import CopilotService

    cp_svc = CopilotService()
    cp_svc.run_pipeline()
