from enum import Enum
from typing import List

from pydantic import BaseModel, field_validator


class Model(str, Enum):
    gpt35turbo = "gpt-3.5-turbo"
    gpt4 = "gpt-4"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionsRequest(BaseModel):
    stream: bool = True
    model: Model | None = None
    messages: List[ChatMessage] = []

    @field_validator("model", mode="before")
    def set_default_model(cls, v: Model | None) -> Model:
        return v or Model.gpt35turbo

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "stream": True,
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Show me a simple example"
                            " of a function that uses modal.Dict.",
                        },
                    ],
                }
            ]
        }
    }


class EmbeddingsModel(str, Enum):
    ada002 = "text-embedding-ada-002"


class EmbeddingsRequest(BaseModel):
    model: str
    input: List[str]


class EmbeddingsResponseData(BaseModel):
    embedding: List[float]
    index: int


class EmbeddingsResponseUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingsResponse(BaseModel):
    data: List[EmbeddingsResponseData]
    usage: EmbeddingsResponseUsage
