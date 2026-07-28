"""FastAPI application: serves the chat UI and the chat endpoint.

Deliberately thin. All reply logic lives in `app.chat.generate_reply`.
"""

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.chat import generate_reply, stream_reply
from app.models import ChatRequest, ChatResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class NoStoreStaticFiles(StaticFiles):
    """StaticFiles that forbids browser caching.

    Starlette sends only etag/last-modified, with no Cache-Control. Browsers are then
    free to serve a heuristically-cached copy *without revalidating*, so a plain reload
    can keep running an old `app.js` — which fails in the most confusing possible way:
    the stale frontend calls the old endpoint, gets a valid answer, and the new feature
    silently appears not to work.

    Implemented as a StaticFiles subclass rather than HTTP middleware on purpose:
    middleware wraps every response, including the SSE stream, and BaseHTTPMiddleware has
    a history of interfering with streaming. This touches /static only.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store"
        return response

# uvicorn configures only its own loggers, so without this the app's own log lines —
# including which custom tool the agent called, and every denied tool — go nowhere.
logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

app = FastAPI(title="chat-app")

app.mount("/static", NoStoreStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Buffered reply: one JSON object once the agent has finished. Good for curl."""
    reply = await generate_reply(request.message, request.conversation_id)
    return ChatResponse(reply=reply.text, resumed=reply.resumed)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """The same answer, reported as it happens, as Server-Sent Events.

    SSE framing lives here rather than in `app.chat`: that module produces StreamChunks,
    this one decides how they go on the wire.

    Note the frontend cannot use the browser's `EventSource` for this — that is GET-only
    and this is a POST — so `static/app.js` reads the body as a stream and parses frames
    itself.
    """

    async def frames() -> AsyncIterator[str]:
        async for chunk in stream_reply(request.message, request.conversation_id):
            # json.dumps escapes newlines, which is load-bearing: a literal newline
            # inside a `data:` line would terminate the frame early.
            yield f"event: {chunk.event}\ndata: {json.dumps(chunk.data)}\n\n"

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Stops a reverse proxy from buffering the whole stream into one chunk,
            # which would defeat the point. Harmless with no proxy in front.
            "X-Accel-Buffering": "no",
        },
    )
