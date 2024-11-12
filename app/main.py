import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, TypedDict

import structlog
from fastapi import FastAPI
from fastapi.routing import APIRoute
from langchain_core.documents import Document

from app import __version__
from app.copilot.service import CopilotService
from app.logging import configure_logging
from app.router import router
from app.settings import settings

os.environ["TZ"] = "UTC"

log = structlog.get_logger()


def generate_unique_openapi_id(route: APIRoute) -> str:
    return f"{route.tags[0]}:{route.name}"


class State(TypedDict):
    splits: List[Document]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[State]:
    log.info("app started")
    cp_svc = CopilotService()
    try:
        docs = cp_svc.load_modal_content_from_disk(settings.MODAL_CONTENT_PATH)
        splits = cp_svc.split_documents(docs)
    except Exception as e:
        log.error(f"Error loading modal content from disk: {e}")
        splits = []
    yield {"splits": splits}
    log.info("app stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="modal-docs-copilot-extension",
        generate_unique_id_function=generate_unique_openapi_id,
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


configure_logging()
app = create_app()
