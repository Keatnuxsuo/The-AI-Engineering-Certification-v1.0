# chat-app

A minimal chat web app: FastAPI backend, plain HTML/CSS/JS frontend, no build step.

The reply logic is currently an **echo stub**. It lives in one function so a real
agent can replace it without touching anything else.

## Run

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000 and send a message.

## Test the endpoint

```bash
curl -s -X POST localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"message":"hello","conversation_id":"test-1"}'
```

```json
{"reply":"You said: hello"}
```

## Layout

```text
app/
  main.py     FastAPI app — GET / and POST /api/chat. Thin; no chat logic.
  chat.py     generate_reply() — the only place replies are produced.
  models.py   ChatRequest / ChatResponse.
static/
  index.html  Chat UI.
  style.css
  app.js      fetch() to /api/chat, renders both sides.
```

## Wiring in a real agent

Replace the body of `generate_reply` in [`app/chat.py`](app/chat.py). Nothing else
needs to change:

- it is already `async`, matching an SDK `query()` call
- it already receives `conversation_id`, for resuming a session per conversation

`app/main.py` calls `generate_reply` and nothing else, so it stays untouched.
