import httpx
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from githubkit import GitHub

from app.copilot.schemas import ChatCompletionsRequest, ChatMessage
from app.copilot.service import CopilotService
from app.settings import settings

router = APIRouter()
log = structlog.get_logger()


api_key_header_scheme = APIKeyHeader(name="x-github-token", auto_error=False)


class Routes:
    chat = "/chat"


@router.post(Routes.chat)
async def chat_completions(
    request: Request,
    chat_comp_req: ChatCompletionsRequest = Body(...),
    cp_svc: CopilotService = Depends(CopilotService),
    api_key: str = Depends(api_key_header_scheme),
) -> StreamingResponse:
    gh = GitHub(api_key)
    gh_user_res = await gh.arequest("GET", "/user")
    username: str = gh_user_res.parsed_data["login"]
    log.info(f"{username} authenticated")
    agent_user_message_history = [
        ChatMessage(
            role=m.role,
            content=m.content,
        )
        for m in chat_comp_req.messages
        if m.role != "system"
    ]
    latest_user_query = agent_user_message_history[-1].content
    markdown_res = cp_svc.retriever(
        user_query=latest_user_query, splits=request.state.splits
    )
    log.info("retrieved markdown response", markdown_res=markdown_res)
    chat_comp_req.messages = (
        [
            ChatMessage(
                role="system",
                content="You are a helpful assistant that replies to user "
                "messages as if you were a senior engineering lead. "
                "Assistant messages should be preserved and treated as "
                "correct responses, especially when there's a reference to a slack "
                "channel or email. Preserve markdown formatting and also "
                "preserve any links associated with the assistant's responses.",
            ),
        ]
        + agent_user_message_history
        + [
            ChatMessage(
                role="assistant",
                content=markdown_res,
            )
        ]
    )
    log.info("request_model", request_model=chat_comp_req.model)
    log.info(
        "Sending request to GitHub Copilot", request=chat_comp_req.model_dump_json()
    )
    log.info("url", url=f"{settings.GH_COPILOT_URL}/chat/completions")
    # TODO: chat with the cp ext team about this, developers should not always have to
    # use the same response as completions to send a message back to the user via
    # cp chat, we get really nicely formatted markdown from the retriever, we should
    # be able to send that back to the user as a message directly
    # maybe there's a way to do this now, but it's not something im doing right now
    async with httpx.AsyncClient() as c:
        gh_copilot_response = await c.post(
            f"{settings.GH_COPILOT_URL}/chat/completions",
            json=chat_comp_req.model_dump(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            gh_copilot_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            log.error(
                "Error from GitHub Copilot",
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise HTTPException(
                status_code=e.response.status_code, detail=e.response.text
            )
    return StreamingResponse(content=gh_copilot_response.iter_bytes())
