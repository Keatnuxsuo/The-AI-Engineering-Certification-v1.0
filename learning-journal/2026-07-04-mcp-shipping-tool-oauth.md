# Learning Journal — Session 8: MCP (Connector Setup, OAuth, AusPost Shipping Tool)

**Source code:** `08_MCP/app/tools.py`, `08_MCP/app/oauth.py`, `08_MCP/app/routes.py`, `08_MCP/app/db.py`, `08_MCP/client.py`

## Plan
- Learning goal: Understand the Cat Shop MCP client/server architecture, connect it to ChatGPT through ngrok + OAuth, then add a real-world MCP tool (`estimate_shipping`, wrapping the AusPost PAC REST API), make it product-aware, fold shipping into checkout, and add "ask the user" guardrails.
- Why this matters: This is the difference between a local toy MCP demo and something a hosted AI client can actually use — public transport, OAuth, external API integration, per-user state, correct totals, and graceful handling of missing input.
- Learning mode: Mixed (AI Engineering + Coding).
- Prior assumptions going in:
  - Once a tool is added and the DB is updated, the connected client will "just see" it.
  - `estimate_shipping` could hit `/calculate` directly with a postcode + weight.
  - REST APIs use `Authorization: Bearer` by default.
  - `checkout` already reflected the true cost.
  - MCP is basically a replacement for REST.
  - `uv sync` should install everything needed, including `ngrok`.
  - Saving an ngrok URL in `.env` would automatically affect the server.
  - A `404` from `/` meant the MCP server was broken.
- Prerequisite knowledge leaned on: async Python, HTTP requests, SQLite, OAuth basics, and the MCP client/server model.

## Explore
- Concepts encountered: MCP client vs server, Streamable HTTP vs stdio, ngrok tunneling, `ISSUER_URL`, OAuth discovery metadata, MCP tools vs tool results, `tools/list` vs `tools/call`, MCP server as an OAuth 2.1 authorization server, PKCE, dynamic client registration, refresh-token rotation, token persistence, structured `need_input` responses, MCP elicitation, wrapping REST with MCP.
- Plain-English explanations:
  - A **server** provides a capability; a **client** uses that capability. In this project, `08_MCP/server.py` + `app/` is the MCP server, while ChatGPT or `client.py` is the MCP client.
  - `ngrok` is not a Python dependency. It is an external networking tunnel that gives a public URL for the local MCP server.
  - `ISSUER_URL` is the public base URL used in OAuth metadata; the MCP endpoint is that base URL plus `/mcp`.
  - An MCP tool = a Python function with `@mcp.tool()`. Its **schema** (name + params) is sent to the client once at connect; its **return value** is computed live on every call.
  - The AusPost PAC API is a **two-step GET flow**: list available services → calculate cost with a chosen `service_code`. Auth is a custom `AUTH-KEY` header, not Bearer.
  - OAuth here does *authorization* (issuing tokens the agent uses), while `/login` does (weak) *identity*.
- Important distinctions:
  - **Server vs client** — the Cat Shop server owns tools/cart/OAuth/database; ChatGPT or `client.py` discovers and calls those tools.
  - **Base issuer URL vs MCP URL** — `ISSUER_URL=https://...ngrok-free.dev`, while the connector URL is `https://...ngrok-free.dev/mcp`.
  - **Root URL vs MCP endpoint** — `GET /` returning `404` is harmless because the server does not implement a homepage.
  - **Streamable HTTP vs stdio** — Streamable HTTP lets remote clients connect over HTTP; stdio is mainly for local process-to-process MCP.
  - **Tool list vs tool results** — the single most important idea this session (see Reflect).
  - **In-memory vs persistent token storage** — explains why `client.py` re-prompts login every run but the GUI client doesn't.
  - **`estimate_shipping` (quote, no side effect) vs `checkout` (charges, clears cart)** — both now share one shipping core so quotes match charges.
- Related tools/APIs: `ngrok`, `curl`, `httpx.AsyncClient`, AusPost PAC (`/postage/parcel/{domestic,international}/{service,calculate}.json`), FastMCP, `aiosqlite`, LangChain MCP adapters, ChatGPT Apps/Connectors.

## Experiment
- Code/activity: connected the local MCP server to ChatGPT using ngrok + OAuth, debugged OAuth metadata and stale connector state, then built `estimate_shipping`, migrated the `products` table to carry parcel dimensions, refactored shipping into `_calculate_shipping`, and added `need_input` guardrails.

- **Code anchor — correct public issuer when starting the server:**
  ```bash
  ISSUER_URL=https://enhance-gluten-hertz.ngrok-free.dev uv run server.py
  ```
  - Why it matters: without `ISSUER_URL`, the OAuth discovery document advertised `http://localhost:8000`, which a hosted client like ChatGPT cannot reach.
  - Predicted: running `uv run server.py` was enough because the server worked locally. Actual: local browser access worked, but remote OAuth registration/token flow needed public metadata.

- **Debugging anchor — healthy connector signals:**
  ```text
  POST /register 201 Created
  POST /token 200 OK
  Processing request of type ListToolsRequest
  ```
  - Why it matters: these logs showed that ChatGPT had registered dynamically, completed OAuth, received a token, and discovered the MCP tool list.
  - Debugging lesson: `401 Unauthorized` before OAuth can be normal; a successful `/token` and authenticated `/mcp` request are stronger signals.

- **Code anchor — right auth header for AusPost:**
  ```python
  headers={"AUTH-KEY": api_key}   # NOT Authorization: Bearer
  ```
  - Why it matters: my first draft used Bearer and would have 403'd. External APIs each have their own auth scheme — read the docs, don't assume.
  - Predicted: Bearer works. Actual: AusPost needs `AUTH-KEY`.

- **Code anchor — two-step flow, shared core:**
  ```python
  services = await _auspost_get(client, ".../service.json", params, api_key)
  service_code = _pick_service_code(services)
  result = await _auspost_get(client, ".../calculate.json", {**params, "service_code": service_code}, api_key)
  ```
  - Why it matters: you can't call `/calculate` without a `service_code` from `/service`. Extracting `_calculate_shipping` let both `estimate_shipping` and `checkout` reuse it, so the pre-purchase quote can't drift from the charged amount.

- **Code anchor — structured "ask the user" signal:**
  ```python
  def _need_input(missing, question):
      return {"status": "need_input", "missing": missing, "question": question}
  ```
  - Why it matters: returning a machine-readable question is more reliable than an error string for getting the LLM to ask for a missing postcode instead of guessing. Verified: no country / no postcode / whitespace postcode all return `need_input`.

- **Verified result (whole-cart shipping in checkout):**
  ```
  cart_weight=1.5  items_total=49.97  shipping=24.75(Express Post)  grand_total=74.72
  ```
  - Debugging insight: `checkout` summed only items before; totals were wrong until shipping was computed from `SUM(weight_kg * quantity)` and added.

- Next small experiment: make `estimate_shipping` handle a full country name ("New Zealand" → "NZ") via a small map or the AusPost country endpoint, since it currently expects a 2-letter code.

## Engineering Connection
- Where this appears in real AI systems: agent tools that wrap third-party APIs (shipping, payments, search), per-user auth on tool calls, and human-in-the-loop prompts when required inputs are missing.
- Tradeoffs:
  - MCP runtime discovery vs REST doc-reading: less glue, but you inherit a **stale-tool-list** failure mode.
  - Combined-parcel shipping (total weight, default box) vs per-item parcels: simpler and cheaper to compute, less physically accurate.
  - `need_input` return (works with any client) vs MCP elicitation (protocol-native but needs client support).
- Failure modes seen this session:
  - `ngrok` missing after `uv sync` because it is an external CLI, not a Python dependency.
  - `ERR_NGROK_4018` until the ngrok auth token was saved in local `ngrok.yml`.
  - OAuth metadata advertising `localhost` when the server was started without `ISSUER_URL`.
  - Misreading `GET / 404` as a broken MCP server instead of a missing homepage.
  - Old ChatGPT connector state showing no actions until the connector was recreated/refreshed.
  - **Zombie server** holding port 8000 with old code after its terminal was killed → client saw an outdated toolset.
  - **Stale tool list** on the GUI client → new tool invisible until reconnect.
  - Wrong totals when shipping wasn't wired into checkout.
- Evaluation/monitoring angle: log which `service_code` AusPost returns and the quoted vs charged amounts to catch drift or API changes.
- Security/cost/deployment: `AUSPOST_API_KEY` in `.env` (server needed its own `load_dotenv()`); OAuth tokens are plaintext in SQLite (fine for demo, hash in prod); username-only login proves *authorization* mechanics, not real *authentication*.

## Post-Task Teaching Debrief
- Approach taken: first untangled the infrastructure path (local server → ngrok tunnel → public OAuth metadata → ChatGPT connector), then read the existing tools and AusPost docs, matched the new tool to the project's patterns (async, dict returns, `{"error": ...}`), then hardened it (product-aware dims, shipping-in-checkout, guardrails).
- Roads not taken: could have debugged only from the browser UI, but the server logs and `curl` metadata checks were more reliable. For shipping, could have hardcoded a single service/price (brittle), or made `estimate_shipping` a standalone script (wouldn't satisfy the MCP requirement). Sharing `_calculate_shipping` beat duplicating the AusPost logic in `checkout`.
- How the pieces connect: `ngrok` exposes local port 8000 → `ISSUER_URL` makes OAuth metadata public → ChatGPT registers and gets tokens → `tools/list` discovers Cat Shop tools → `db.py` holds parcel dims → `get_product` exposes them → `_calculate_shipping` uses them → `estimate_shipping` quotes / `checkout` charges. OAuth gates the cart tools via `_get_username()`.
- Mistakes and dead ends: expecting `uv sync` to provide ngrok; missing ngrok auth token; starting server without `ISSUER_URL`; interpreting harmless `404 /` as failure; Bearer-vs-AUTH-KEY; assuming a reconnect wasn't needed (the real bug was a zombie process + cached tool list, not the code); assuming DB-fresh implied tools-fresh.
- Future pitfalls ("wish I'd known"): check the OAuth discovery document directly when hosted clients fail; after adding/renaming a tool, **restart the server AND reconnect the client** — code changes to a tool's *return value* propagate live, but *new tools/signature changes* only appear on a fresh `tools/list`.
- Expert lens: separate transport, auth, and business logic when debugging. A senior engineer would ask: "Can the public client reach discovery metadata? Does metadata point to public URLs? Did token exchange succeed? Did the client run `tools/list`?" For tool design, separate "quote" from "commit" operations; never let an LLM invent identifiers like postcodes; keep destructive actions (checkout) in deterministic code, discovery in the agent.
- Transferable lessons: wrap REST with a thin, reusable core; return structured signals the model can act on; distinguish protocol channels (list vs results) when debugging "it's not showing up"; don't confuse local success with hosted-client reachability.

## Reflect
- What I understand now:
  - MCP has clear roles: server exposes tools/resources/prompts; client discovers and calls them; the LLM/agent decides which tool to use.
  - A hosted client cannot reach my laptop's `localhost`; it needs a public tunnel and public OAuth metadata.
  - `ngrok` auth token setup is persistent local CLI config, while each tunnel run may produce a URL that the MCP server must advertise.
  - Streamable HTTP is the right transport when the MCP client is remote; stdio is mainly for local process communication.
  - MCP sends the **tool list once at connect** but computes **results live** — so fresh DB output does NOT prove a fresh tool list. A new tool needs a client reconnect.
  - AusPost PAC is a two-step GET flow with an `AUTH-KEY` header.
  - The server needs its own `load_dotenv()`; the client's doesn't cover it.
  - OAuth here is a real 2.1 + PKCE flow; the weak spot is username-only identity (fixable with a password/hashing or delegating to Supabase Auth).
- What was unclear / corrected:
  - Misconception: "MCP server root URL should load a page." → Corrected: `/mcp` and `.well-known` routes matter; `/` can return `404`.
  - Misconception: "OAuth means proving who the person is." → Corrected: OAuth is mainly about delegated authorization; this demo's username form is weak identity.
  - Misconception: "Saving `ISSUER_URL` in `.env` is enough." → Corrected: the server must actually load `.env` or receive the env var at process start.
  - Misconception: "DB updated, so the tool must be live." → Corrected: tool *list* was cached; only a reconnect refreshes it.
  - Misconception: "REST replaces / is replaced by MCP." → Corrected: MCP is an agent-facing interaction model often layered *on top of* REST; complementary is a design choice, not a law.
- One-minute explanation: I connected a local MCP server to ChatGPT by exposing it with ngrok and making OAuth metadata point to the public `ISSUER_URL`, then added a shipping tool that wraps the AusPost REST API behind MCP. The shipping tool uses product weight/size, checkout includes shipping in the grand total, and missing inputs return structured `need_input` prompts instead of letting the model guess. The trickiest bugs were mostly boundaries: local vs public URLs, OAuth discovery vs MCP endpoint, and cached tool lists vs live tool results.
- Active recall questions:
  1. In the Cat Shop setup, which part is the MCP server and which part is the MCP client?
  2. What is the difference between `ISSUER_URL` and the connector URL ending in `/mcp`?
  3. Why is `GET / 404` harmless for this MCP server?
  4. Which log lines prove that ChatGPT successfully connected through OAuth?
  5. Why can a client get updated `get_product` output but still not see `estimate_shipping`?
  6. What two AusPost endpoints must you call, and in what order, to get a domestic quote?
  7. Which header does AusPost auth use, and why did Bearer fail?
  8. Why does `client.py` prompt for login every run while the GUI client doesn't?
  9. What does a `need_input` response contain, and why is it better than raising an error?
  10. Why extract `_calculate_shipping` instead of duplicating logic in `checkout`?
- Spaced review suggestion: re-answer the server/client + `ISSUER_URL` questions tomorrow, re-implement the two-step AusPost flow from memory in 3 days, and revisit the OAuth flow + a password/Supabase upgrade next week.
