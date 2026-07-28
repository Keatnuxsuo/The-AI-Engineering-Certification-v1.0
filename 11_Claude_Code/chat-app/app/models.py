"""Request and response shapes for the chat API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str
    # False when this answer started a fresh agent session. The browser uses it to spot
    # the case where its stored history outlived the server's in-memory session map.
    resumed: bool = True
