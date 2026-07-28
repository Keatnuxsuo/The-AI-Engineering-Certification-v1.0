# Learning Journal — Session 11: Claude Code & the Claude Agent SDK (Codebase Concierge, Custom Tools, SSE Streaming)

**Source code:** `11_Claude_Code/chat-app/app/chat.py`, `11_Claude_Code/chat-app/app/main.py`, `11_Claude_Code/chat-app/app/tools.py`, `11_Claude_Code/chat-app/app/config.py`, `11_Claude_Code/chat-app/app/models.py`, `11_Claude_Code/chat-app/static/app.js`, `11_Claude_Code/chat-app/static/style.css`, `11_Claude_Code/chat-app/static/index.html`, `11_Claude_Code/chat-app/CLAUDE.md`, `11_Claude_Code/chat-app/scratch_query.py`

## Plan

- Learning goal: Work Session 11 end-to-end — scaffold a chat app **with** Claude Code, then replace the echo stub with a real Agent SDK agent (a "codebase concierge"), add per-conversation memory, a custom in-process MCP tool, a multi-conversation sidebar, and live SSE streaming.
- Why this matters: This is the pivot from *using* an agent to *serving* one. Sessions 2–4 had me hand-building agent loops in LangGraph; this session hands me the same loop as a dependency and forces the question of what I gain and what control I give up.
- Learning mode: Mixed (AI Engineering + Coding + a large unplanned detour into **security verification**).
- Prior assumptions going in — every one of these surfaced as a question I asked, and every one was at least partly wrong:
  - An `ANTHROPIC_API_KEY` would be needed to use the SDK.
  - `allowed_tools` restricts what the agent **can** do.
  - Streaming LLM output needs a library (LangChain?).
  - Tool streaming hadn't been implemented (it had — it was invisible).
  - `cwd` is just a convenience for relative paths.
  - "The agent refused to delete the file" proves it can't.
- Prerequisite knowledge leaned on: async Python / async generators, FastAPI + Pydantic, `pathlib`, plain DOM JS + `fetch`, HTTP headers/caching, MCP from Session 8, checkpointer-style memory from Session 3.

## Explore

- Concepts encountered: the agent loop as an importable library; `query()` as an async generator; the SDK message stream (`SystemMessage` → `AssistantMessage`/`UserMessage` alternation → `ResultMessage`); `cwd` as path root *and* boundary; session resumption via `resume=`; in-process MCP servers (`create_sdk_mcp_server`); auto-approve vs deny lists; `disallowed_tools`; deferred tools + `ToolSearch`; adaptive thinking and `display`; SSE vs WebSocket; `include_partial_messages` and `StreamEvent`.
- Plain-English explanations:
  - **The SDK is Claude Code's loop, minus the terminal.** `Claude Code CLI = loop + terminal UI`; `Agent SDK = loop + your code`. Same tools, same permission plumbing, same `CLAUDE.md` loading. The "Bridge to Breakout Room 2" point in the guide is that Task 2 (asking Claude Code about an unfamiliar repo) *was already a demo of the finished product*, just through the wrong interface.
  - **Memory is a coat check.** The runtime stores the transcript on disk; my app stores a 36-character ticket (`session_id`) per browser conversation. The model is stateless — `resume=` re-sends the whole prior conversation as input. "Memory" is re-reading the transcript out loud every turn. That's also why cost grows with conversation length, and why `/compact` has to exist.
  - **Streaming is not a network feature.** `query()` yields Python objects *in my process*. SSE vs WebSocket is a separate decision about pushing those to a browser. Conflating the two is exactly what makes people reach for LangChain when they already have the stream.
  - **A custom tool is outside the sandbox.** `cwd` confines `Read`/`Glob`/`Grep` because the runtime enforces it. `repo_stats` is my own Python running in my FastAPI process — the SDK cannot restrain it. Every custom tool is a potential hole in my own boundary.
- Important distinctions (each of these pairs looks like one thing and is two):
  - **`allowed_tools` vs `disallowed_tools`** — auto-approve list vs actual restriction.
  - **`conversation_id` vs `session_id`** — mine (a browser chat window) vs the runtime's (a stored transcript). `_SESSIONS` is just a translation table.
  - **Tool Runner vs Agent SDK** — a loop over tools *I* define vs the whole Claude Code harness with built-in tools.
  - **`content_block_stop` vs "tool finished"** — end of the tool's *input JSON streaming* vs end of *execution*.
  - **Persuasion vs enforcement** — `CLAUDE.md`/system prompt (model may comply) vs code that runs (deterministic).
  - **Browser-side transcripts vs server-side sessions** — two stores with different lifetimes that can disagree.
- Related tools/APIs: `claude-agent-sdk` (`query`, `ClaudeAgentOptions`, `ResultMessage`, `SystemMessage`, `StreamEvent`, `tool`, `create_sdk_mcp_server`, `HookMatcher`, `PermissionResultAllow/Deny`), `uv add`/`uv run`, `uvicorn --reload`, FastAPI `StreamingResponse`, Starlette `StaticFiles`, `fetch` + `ReadableStream` + `TextDecoder`, `localStorage`, `lsof`.

## Experiment

- Code/activity: ran `scratch_query.py` to feel the message stream; wired `query()` into `POST /api/chat`; added `_SESSIONS` resumption; built a `repo_stats` custom tool with path validation; discovered the read-only boundary didn't exist and fixed it; built a multi-conversation sidebar on `localStorage`; added an SSE streaming endpoint with tool + thinking + text events.

### Code anchor 1 — the placeholder that taught me `cwd`

```python
cwd="/path/to/any/repo/you/like",
```

- What it does: sets the directory the agent operates in — its path root *and* (per the docs) the limit of what the built-in tools can reach without `add_dirs`.
- Prediction: the scratch script would run.
- Actual: `CLIConnectionError: Working directory does not exist: /path/to/any/repo/you/like`.
- Lesson: guide snippets contain placeholders. Also — **read the last line of a traceback first**; it named the exact problem while ~60 lines of `asyncio` frames sat above it. Follow-on: `cwd="./chat-app"` from *inside* `chat-app` resolves to `chat-app/chat-app`. The relative answer was `"."`.

### Code anchor 2 — the five lines that reframed the whole session

```
allowed_tools      : ['Read', 'Glob', 'Grep', 'mcp__concierge__repo_stats']   (no Bash)
TOOL REQUESTED     : Bash  {'command': 'echo MARKER-4271-EXECUTED'}
TOOL RESULT        : MARKER-4271-EXECUTED
permission_denials : []
```

- Prediction: `Bash` isn't allowlisted, so nothing happens.
- Actual: **it ran.** `allowed_tools` is an *auto-approve* list; unlisted tools stay available and, headless with no permission callback, execute unchallenged.
- Also failed: `permission_mode="dontAsk"` (despite a docstring saying it "denies anything not pre-approved by allow rules") and a `PreToolUse` hook as I wrote it. `can_use_tool` raised `ValueError: requires streaming mode`. Only **`disallowed_tools`** worked — those tools are never offered to the model at all.
- Lesson: a parameter that *sounds* like a boundary isn't necessarily one. This invalidated a claim I had already written into `CLAUDE.md` ("structurally cannot modify anything"). The real boundary had been the system prompt's personality.

### Code anchor 3 — the check that makes a custom tool safe

```python
resolved = (root / raw).resolve()          # collapses .. and follows symlinks FIRST
if not resolved.is_relative_to(root):
    raise ValueError(f"{raw!r} is outside the repository")
```

- Why it matters: resolve-then-check. Validating the raw string before resolution is the classic path-traversal bug. Refused `../..`, `/etc`, `app/../../..`, `../../../../etc/passwd`; an absolute `raw` replaces the root under pathlib's `/` semantics and gets caught by the same check.
- Lesson: the SDK can't sandbox code I write. Input validation on a custom tool is my job, not the framework's.

### Code anchor 4 — timing that changed a design

```
4.88  tool      {"name": "repo_stats"}
4.90  tool_done {}                        ← 20ms later
```

- Prediction: the "Using repo_stats…" label would cover the wait.
- Actual: tool *execution* is ~20ms. The 1.5–2s gaps are **model inference between** tools. A label cleared on tool completion flashed for one frame and then left the user staring at nothing through the real wait.
- Lesson: instrument with timestamps *before* designing a progress UI. Redesigned as an accumulating trace (`Used repo_stats · Read · Read`) plus streamed thinking text in the gaps.

### Code anchor 5 — the setting that makes reasoning visible

```python
thinking={"type": "adaptive", "display": "summarized"},   # default is "omitted"
```

- With the default, thinking blocks stream with **empty text** — present but useless.
- Caveat found by measuring: block order in one run was `['tool_use','tool_use','thinking','tool_use','tool_use','text']`, and another run produced no thinking at all. Adaptive thinking decides per turn, so some answers show reasoning and some don't. **Expected, not a bug.**

### Debugging insight — the biggest transferable lesson: tests that cannot fail

Four of my own verification attempts proved nothing, and each had to be redesigned:

| Bad test | Why it proved nothing | Fix |
|---|---|---|
| "What are **its** dependencies?" for memory | `cwd` supplies the referent — the no-memory control answered correctly too | Plant `4271`, a fact the repo cannot contain |
| Grep the reply for `MARKER-4271` | The marker was **in the prompt**; echoing it is a false positive | `openssl rand -hex 12` — output the model can't fabricate |
| "Delete README.md" for read-only | Refused on **persona**, never attempted a tool → inconclusive | A benign command it has no reason to refuse (`echo`) |
| `grep innerHTML app.js` | Matched the comment *"never innerHTML"* | `grep -E "innerHTML\s*="` |

Plus a fifth, environmental: a `curl` "verifying" Task 6 actually hit a **3-hour-old uvicorn** on port 8000 with no `--reload`, returning `You said: ...` from stale in-memory code while my own server died with `Errno 48`. Had I not read the log I'd have reported the change broken.

- Rule: **a test that passes when the feature is broken is worse than no test** — it manufactures confidence. Ask of every check: "what would make this fail?"

### Debugging insight — the stale-asset trap

Streaming worked over HTTP but "didn't work" in the browser. The server was serving the new `app.js` the whole time; the browser was running a cached copy. Starlette's `StaticFiles` sends `etag`/`last-modified` but **no `Cache-Control`**, so browsers cache heuristically *without revalidating*.

- Why it was so confusing: the stale frontend called the **old** endpoint, which still worked perfectly — so a working feature looked silently broken, with no error anywhere.
- Fix: a `NoStoreStaticFiles` subclass adding `Cache-Control: no-store`. Deliberately a `StaticFiles` subclass, **not** HTTP middleware — `BaseHTTPMiddleware` wraps every response including the SSE stream and has a history of interfering with streaming.

- Next small experiment: set `AGENT_MODEL=claude-haiku-4-5` and re-ask the same three questions. Does it still cite correct line numbers? Does it still prefer `repo_stats` over `Glob`+`Read`? ~5 minutes, ~$0.02 — a concrete test of whether model choice matters for *this* workload rather than in the abstract.

## Engineering Connection

- Where this appears in real AI systems: any LLM feature behind an HTTP endpoint — untrusted user input → a tool-calling agent → a real filesystem with the server process's privileges.
- Tradeoffs actually made (and measured, not assumed):
  - **Pinned model.** Unset, the SDK inherited the ambient runtime default — which resolved to Opus with a 1M context window. Pinning bought reproducibility; the cost saving was only **$0.135 → $0.109 (19%)**, not the multiple I predicted, because ~21.5k cache-creation tokens dominate regardless of model.
  - **`repo_stats` efficiency claim: falsified.** Same `num_turns` (3), and **higher** cost ($0.133 vs $0.0595) than the control, which just shelled out to `wc -l`. Still a better capability than depending on `Bash` existing — but I stated the efficiency benefit in a plan and only found out because the plan said I'd measure it.
  - **Blocklist over allowlist**, forced by the API. `disallowed_tools` works but rots.
  - **Browser transcripts + server sessions** — no new endpoints needed for multi-conversation, but the two stores can disagree.
- Failure modes discovered by hitting them:
  - Read-only boundary that didn't exist.
  - Blocklist rot — `_warn_about_unknown_tools` caught `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` on the first real run, because the shell I enumerated the toolset in had `CLAUDE_CODE_ENABLE_TASKS=0`. **Not** an SDK upgrade — a different terminal.
  - Stale server process; stale browser asset.
  - `in_tool` as a boolean breaking on **parallel** tool calls (two `tool_use` blocks open at once) — needed a counter.
  - A `system_prompt` rule the code visibly violates: "no markdown" while replies ship `-` bullets.
- Evaluation / monitoring angle: `_warn_about_unknown_tools` turns "the blocklist silently rotted" into a log line. `logging.basicConfig` in `main.py` was needed at all because uvicorn configures only its own loggers — without it, the custom tool's log line went nowhere and the guide's "confirm in your server logs" verification silently couldn't work.
- Security / cost / deployment: `disallowed_tools` is the real gate; `cwd` bounds the built-ins; custom tools validate their own paths. Residual accepted risk — the agent can read **anything inside `TARGET_REPO`**, including a committed `.env`. Cost ~$0.11–0.13/question, dominated by cache creation per fresh session, which makes session resumption a **cost** fix as much as a UX one. Found late: `max_budget_usd` is a harder ceiling than `max_turns`.

## Reflect

- What I understand now:
  - The Agent SDK is Claude Code's loop as a library; my app's job was plumbing, not invention.
  - Memory is ticket-stub indirection over a runtime-managed transcript; the model itself is stateless.
  - Streaming output is in-process and transport-agnostic; SSE vs WebSocket is a separate, downstream decision.
  - Custom tools live *outside* the sandbox that protects the built-ins.
  - A boundary you haven't tested is a boundary you don't have.
- What was unclear (and got resolved): what `cwd` is for; where the auth came from with no API key (the Task 1 CLI login in the macOS Keychain, not an `ANTHROPIC_API_KEY`); how memory actually worked; why the SDK page mattered vs LangChain.
- Misconception corrected — the headline: **`allowed_tools` is not a restriction.** I wrote, and put in `CLAUDE.md`, that a `Read`/`Glob`/`Grep` agent "structurally cannot modify anything." Empirically false. The earlier "proof" (the agent politely declining to delete `README.md`) proved only that it has manners.
- Still unclear / untested — carry forward:
  - Whether Starlette actually cancels the agent run when a browser disconnects mid-stream. Planned as a verification step, never executed. Real money rides on it.
  - The markdown/`textContent` narrowing is still pending: `CLAUDE.md` forbids markdown while replies ship bullets. **A convention the code visibly violates trains the next reader to ignore the whole file.**
  - No SSE heartbeats, no reconnect/replay — a dropped stream just fails.
- One-minute explanation: *"A prompt is persuasion. An allowlist is a suggestion. Only code that runs is enforcement — and the way you tell them apart is a test designed so it can fail."*
- Active recall questions:
  1. `allowed_tools=["Read","Glob","Grep"]`, nothing else configured. Can the agent run `Bash`? Why?
  2. The app shows a 20-message conversation but the agent remembers none of it. What happened, and which response field tells the browser?
  3. Why can't the browser's `EventSource` talk to `/api/chat/stream`?
  4. `repo_stats` is handed `path="../.."`. What stops it, and why doesn't `cwd` handle this case?
  5. A tool label appears and vanishes in 20ms. What does `content_block_stop` actually mark?
  6. `display: "summarized"` is set and some answers still stream no reasoning. Bug or expected?
  7. Frontend changes don't appear after a reload, but `curl` shows the server has the new file. What's happening?
- Spaced review:
  - **Tomorrow:** Q1 and Q4 — the two security questions. Re-run the `openssl rand -hex` probe from memory, without looking at the code.
  - **In 3 days:** give the coat-check explanation of session memory out loud, no notes. Then explain why streaming needed no library.
  - **Next week:** re-read `chat-app/CLAUDE.md`. Every line I can't justify is a line to delete — and check whether the markdown gap is still lying.
