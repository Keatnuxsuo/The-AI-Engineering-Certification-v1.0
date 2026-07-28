# CLAUDE.md

## Commands

```bash
uv sync                                   # install deps into .venv
uv run uvicorn app.main:app --reload      # dev server on http://localhost:8000
```

`TARGET_REPO` sets the repository the agent answers questions about; it defaults to
this project. Requires Anthropic credentials in the environment — SDK usage is billed
as API usage, not against a Claude subscription.

Smoke-test the buffered endpoint (slow — it runs a real agent):

```bash
curl -s -X POST localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What does POST /api/chat do?","conversation_id":"test-1"}'
```

Watch the streaming endpoint frame by frame (`-N` disables curl's own buffering):

```bash
curl -sN -X POST localhost:8000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Largest file in app/?","conversation_id":"test-2"}'
```

No test suite, linter, or build step. The frontend is plain HTML/CSS/JS served as
static files — no bundler, no npm, no framework. Keep it that way.

## The one architectural decision

All reply logic lives in `app/chat.py`. `app/main.py` routes and owns wire formats; it
contains no chat logic.

```
static/app.js  --POST /api/chat/stream-->  app/main.py  -->  app/chat.py::stream_reply
   (reads SSE frames)                      (SSE framing)     (the only place query()
                                                              is called)
               --POST /api/chat--------->  app/main.py  -->  app/chat.py::generate_reply
   (curl, smoke tests)                     (JSON)            (drains stream_reply)
```

**`stream_reply` is the single source of truth**; `generate_reply` is a thin wrapper that
drains it and returns the final `Reply`. Two endpoints, one agent code path — do not give
the buffered endpoint its own `query()` call, or they will drift.

Historical note, because it was a stated invariant: wiring in the Agent SDK (Task 6) and
session resumption (Task 7) each touched `app/chat.py` alone. **Streaming broke that** —
a function cannot both `return` a value and `yield` progress, so the endpoint contract,
`main.py`, and the frontend all had to change together. That was the known cost, not an
accident.

`conversation_id` selects which SDK session to resume, via the `_SESSIONS` dict in
`app/chat.py`. That dict is process-local and in-memory: it empties on restart and on
every `--reload`, and would break under more than one worker.

**State is split across two places that can disagree**, and this is the thing to
understand before changing either side:

| | Lives in | Dies when |
| --- | --- | --- |
| Transcripts (what you see) | browser `localStorage` | you clear storage |
| Agent memory (`session_id`) | `_SESSIONS`, server RAM | the server restarts |

So a restart leaves a full sidebar in front of an agent that remembers nothing.
`generate_reply` returns `Reply(text, resumed)` and `ChatResponse.resumed` carries it to
the browser, which shows a `.message.notice` when a conversation with history gets
`resumed: false`. Without that the app looks broken rather than restarted.

There is deliberately **no** server-side conversation list. `POST /api/chat` accepts any
`conversation_id`, so multi-conversation support needed no new endpoints — the sidebar is
entirely frontend state.

## Streaming

`include_partial_messages=True` makes `query()` yield extra `StreamEvent` messages
carrying raw Claude API events. `stream_reply` turns those into `StreamChunk`s
(`thinking` / `tool` / `text` / `error` / `done`); `main.py` frames them as SSE. Every
stream ends with exactly one `done`.

Six things here are decisions, each established by measuring the real event stream:

- **`done.reply` is authoritative; accumulated `text` deltas are a preview.** The frontend
  replaces its buffer with `done.reply` rather than keeping it, so a dropped delta cannot
  corrupt a transcript.
- **Text suppression uses a counter, not a boolean.** Tool *inputs* stream too, as
  `input_json_delta`, and the model emits **parallel** tool calls — two `tool_use` blocks
  can be open at once, so the first `content_block_stop` must not re-enable text while the
  second is still streaming its input.
- **There is no "tool finished" event, on purpose.** Measured: tool execution takes ~20ms
  while the gaps *between* tools are 1.5–2s of model inference. A label cleared on tool
  completion flashed for one frame and then left the user watching nothing through the
  actual wait. The UI keeps a running list of tools instead.
- **`thinking` needs `display: "summarized"`.** The default is `"omitted"`, which streams
  thinking blocks with empty text — present but useless. Note thinking is **intermittent**:
  adaptive thinking decides per turn, so some answers stream no `thinking` frames at all.
  That is expected, not a failure.
- **`HIDDEN_TOOLS` hides `ToolSearch`.** It is how the runtime loads the deferred
  `Glob`/`Grep` schemas — real work, but meaningless to a user mid-answer.
- **The frontend cannot use `EventSource`.** It is GET-only and this endpoint is POST, so
  `app.js` reads the response body and parses frames itself.

Static files are served with `Cache-Control: no-store` (`NoStoreStaticFiles` in
`app/main.py`). Without it Starlette sends only etag/last-modified, browsers cache
heuristically without revalidating, and a stale `app.js` keeps calling the old endpoint —
which returns a perfectly good answer, so the new frontend appears silently broken.

Observed ordering note: the complete `AssistantMessage` arrives *before* the matching
`content_block_stop`, not after as the SDK docs' flow diagram suggests. Nothing depends on
it today; don't be surprised by it.

No heartbeats and no reconnect/replay — a dropped stream just fails the request.

## Conventions

- `static/app.js` uses `textContent`, never `innerHTML` — replies are arbitrary
  model output, and so are conversation titles.
- `app.js` renders from `state`, never patching the DOM in place. `pending` is a flag on
  a conversation rather than a DOM node, so switching away and back keeps the
  "Thinking…" indicator. If you add a response mode (e.g. streaming), keep it in state.
- A reply belongs to the conversation it was **sent from**, not the one on screen when it
  arrives. `send()` captures the conversation up front; a request takes ~15s, so users do
  switch mid-flight.
- Input validation belongs in the Pydantic models, not in handlers.

## The agent

`generate_reply` runs a Claude Agent SDK `query()` over `TARGET_REPO` and returns the
`ResultMessage.result`. Constraints that are decisions, not accidents:

- **`disallowed_tools` is what makes this read-only — not `allowed_tools`.** Read the
  next section before touching either.
- `system_prompt` forbids markdown, because `app.js` renders replies with
  `textContent`. Change one and you must change the other.
- Agent errors are caught and returned as a chat reply, never a 500.
- Options are built per request so `TARGET_REPO` is live and `resume=` can be added.
- `model` is pinned (`AGENT_MODEL` overrides). Unset, the SDK inherits the ambient
  Claude Code runtime default, so behaviour stops being reproducible across machines.

No API key is configured or needed: the SDK spawns the bundled Claude Code runtime,
which authenticates with the CLI login in the system keychain.

Known gap: the no-markdown instruction is not reliably obeyed. Prose answers comply,
but list-shaped questions ("what are the dependencies?") still come back as `-` bullets.
Either strengthen the prompt or decide bullets are acceptable — do not assume it holds.

## How read-only is actually enforced

This was established by testing, and the results contradict the obvious reading of the
API. Do not "simplify" this section away.

`allowed_tools` is an **auto-approve list, not a restriction.** Tools left off it stay
available and, headless with no permission gate, run unchallenged. With
`allowed_tools=["Read","Glob","Grep"]` and nothing else, the agent successfully ran
`Bash`. `permission_mode="dontAsk"` did not stop it either, despite its docstring saying
it denies anything not pre-approved.

What does work is `disallowed_tools`: those tools are never offered to the model at all.
`DENIED_TOOLS` in `app/chat.py` is therefore the real boundary — every tool the runtime
offers by default, minus the handful we want.

Consequences worth remembering:

- `ToolSearch` must stay permitted. `Glob` and `Grep` are *deferred* tools whose schemas
  the agent loads through it; deny it and searching silently stops working.
- `DENIED_TOOLS` is a blocklist, so it rots. `_warn_about_unknown_tools` logs any tool
  the runtime offers that we have not classified. This is not hypothetical: it caught
  `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` on first real run, because the shell
  used to enumerate the toolset had `CLAUDE_CODE_ENABLE_TASKS=0`. **The offered set
  varies with the environment**, so no one-off enumeration is trustworthy — if that
  warning appears, add the tools to `DENIED_TOOLS`.
- The agent's own refusals prove nothing. Asked to delete a file it declines politely
  because of `system_prompt`, whether or not the tool exists. Test with something benign
  it has no reason to refuse (`echo`, `openssl rand`) and check whether the tool appears
  in the init message's `tools` list.

## Custom tools

`app/tools.py` defines `repo_stats` (file inventory with line counts) and exposes it via
`create_sdk_mcp_server` as an in-process MCP server. Allowlisted as
`mcp__concierge__repo_stats` — custom tools need naming in `allowed_tools` exactly like
built-ins.

**`cwd` does not sandbox custom tools.** It confines Read/Glob/Grep, but a tool here is
ordinary Python in the FastAPI process, so any path it accepts must be validated against
`target_repo()` explicitly. `_resolve_inside_repo` does that, and `..`, absolute paths,
and escaping symlinks are all refused. Any new tool taking a path must do the same.

`app/config.py` exists so `chat.py` and `tools.py` can share `target_repo()` without a
circular import.
