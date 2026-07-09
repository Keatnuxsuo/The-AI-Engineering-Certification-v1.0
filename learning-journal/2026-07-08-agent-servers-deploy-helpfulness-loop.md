# Learning Journal — Session 9: Agent Servers (Deploy to Azure + Vercel, Assistants, Helpfulness Loop)

**Source code:** `09_Agent_Servers/langgraph.json`, `09_Agent_Servers/Dockerfile`, `09_Agent_Servers/azure.yaml`, `09_Agent_Servers/app/graphs/agent_with_helpfulness.py`, `09_Agent_Servers/app/graphs/simple_agent.py`, `09_Agent_Servers/frontend/app/page.tsx`, `09_Agent_Servers/frontend/app/api/[...path]/route.ts`, `09_Agent_Servers/frontend/components/chat.tsx`

## Plan
- Learning goal: Deploy a LangGraph agent as a real server — Python backend on **Azure Container Apps**, Next.js frontend on **Vercel** — then extend the agent with a self-correcting **helpfulness loop** (Activity 1) and verify it in LangGraph Studio, and finally automate both deploys with CI/CD (Vercel Git integration + `azd pipeline config` → GitHub Actions).
- Why this matters: This is the DEPLOY step of the lifecycle (BUILD → DEPLOY → OBSERVE → EVALUATE → ITERATE). Without a hosted backend + frontend, you can't OBSERVE traces or EVALUATE behavior. It's the jump from "runs on my laptop" to "an always-on API a web client can call."
- Learning mode: Mixed (AI Engineering + Coding + Deployment/DevOps).
- Prior assumptions going in:
  - Editing `langgraph.json` and running `azd deploy` is enough to make a new graph live.
  - `azd deploy` reporting SUCCESS means the new code is actually running.
  - A message's `.content` is always a string.
  - The two graphs in the Studio dropdown must somehow work together.
  - `NEXT_PUBLIC_API_URL` behaves like a normal runtime env var.
  - CLI deploy tools (`vercel`, `azd pipeline config`) will "just work" when run from my app's subfolder.
- Prerequisite knowledge leaned on: LangGraph `StateGraph`/nodes/edges, Docker basics, environment variables, HTTP/`curl`, Next.js app structure.

## Explore
- Concepts encountered: `langgraph.json` manifest, `LANGSERVE_GRAPHS`, generated vs source-of-truth files, Graphs vs Assistants vs Threads, default assistant auto-creation, Azure Container Apps + `azd`, Vercel root directory + build-time env inlining, API passthrough proxy, LangGraph Studio graph selector / Trace tab, conditional edges, message content blocks.
- Plain-English explanations:
  - **Graph vs Assistant vs Node.** A *graph* is the code blueprint (`simple_agent`, `agent_with_helpfulness`). An *assistant* is a runnable instance of a graph stored in the server's DB (what `/assistants/search` returns). A *node* is one step inside a graph.
  - **Two graphs ≠ teammates.** `simple_agent` and `agent_with_helpfulness` are independent tenants on the same server. The client picks *one* per conversation. They do not call each other.
  - **Two nodes = teammates.** Inside `agent_with_helpfulness`, the `agent` node answers and the `judge` node grades; the conditional edge loops back for a retry. *These* cooperate.
  - **The Dockerfile is a generated snapshot.** `langgraph dev`/`build` read `langgraph.json` live, but Azure builds from a static `./Dockerfile` whose `ENV LANGSERVE_GRAPHS=...` is frozen at generation time.
  - **`NEXT_PUBLIC_*` is baked at build time.** It's compiled into the browser JS, so it must be correct *before* the build and point at an absolute URL.
- Important distinctions:
  - **Source of truth (`langgraph.json`) vs generated artifact (`Dockerfile`)** — they can silently drift.
  - **`azd deploy` succeeded vs the new graph is loaded** — success only means "an image built and rolled out," not "my edit is in it."
  - **Default assistant auto-creation** happens at DB init / server startup, once per graph — not retroactively guaranteed for graphs added later to an existing DB.
  - **Server-side env (`LANGGRAPH_API_URL`, `LANGSMITH_API_KEY`) vs public env (`NEXT_PUBLIC_API_URL`)** — the browser only ever sees the public one; the Azure URL + key stay server-side in the proxy.
  - **`.content` as `str` vs `list` of content blocks.**
- Related tools/APIs: `azd deploy`, `uv run langgraph dockerfile Dockerfile`, `curl POST /assistants/search`, `curl POST /assistants`, LangGraph Studio, Vercel dashboard, `langgraph-nextjs-api-passthrough`, `useStream`.
- CI/CD concepts added: GitHub Actions workflow (`.github/workflows/azure-dev.yml`), `azd pipeline config`, OIDC **federated credentials** (User-Assigned Managed Identity + OIDC = *secretless* auth), GitHub Actions **secrets vs variables**, Vercel **Root Directory**, the monorepo **subfolder-vs-repo-root** mismatch.
- Plain-English (CI/CD):
  - **Federated credentials (OIDC) = no stored Azure secret.** Instead of saving a service-principal password in GitHub, each workflow run gets a short-lived token that Azure trusts *because* it came from `repo:.../ref:refs/heads/main`. The trust is scoped to a specific repo+branch/PR.
  - **Secrets vs variables.** GitHub *secrets* (`OPENAI_API_KEY`, …) are masked in logs; *variables* (`AZURE_CLIENT_ID`, `AZURE_ENV_NAME`, …) are plaintext config. `azd` set both automatically.
  - **CLI tools assume project = repo root.** `vercel` and `azd` both anchor to the git root; run from a subfolder and they either can't find the repo or write files to the wrong place.

## Experiment
- Code/activity: registered `agent_with_helpfulness` in `langgraph.json`, chased down why it wasn't live on Azure, regenerated the Dockerfile, redeployed, verified both assistants, deployed the frontend to Vercel, then debugged a runtime error in `judge_node`.

- **Debugging anchor — the deployed graph was missing despite SUCCESS:**
  ```bash
  curl -s -X POST ".../assistants/search" -d '{"limit":10}'
  # only simple_agent came back
  curl -s -X POST ".../assistants" -d '{"graph_id":"agent_with_helpfulness"}'
  # {"detail":"graph 'agent_with_helpfulness' not found"}  HTTP 404
  ```
  - Why it matters: the 404 proved the running container never loaded the new graph — so the problem was in the *build*, not the code.
  - Predicted: editing `langgraph.json` + `azd deploy` would make it live. Actual: it didn't, because Azure doesn't read `langgraph.json`.

- **Root-cause anchor — stale generated Dockerfile:**
  ```dockerfile
  ENV LANGSERVE_GRAPHS='{"simple_agent": "app.graphs.simple_agent:graph"}'
  ```
  - Why it matters: this frozen line (only `simple_agent`) is what the container actually loads. My `langgraph.json` had both graphs; the Dockerfile had drifted.
  - Fix: `uv run langgraph dockerfile Dockerfile` to regenerate from the manifest, then `azd deploy`. After redeploy, `/assistants/search` returned **both** assistants with fresh `created_at` timestamps (server reinitialized and auto-created both defaults).

- **Concept anchor — the helpfulness loop wiring:**
  ```python
  builder.add_edge(START, "agent")
  builder.add_edge("agent", "judge")
  builder.add_conditional_edges("judge", route, {"agent": "agent", END: END})
  ```
  - Why it matters: `route` returns `END` on `"Y"` or when `attempts >= MAX_ATTEMPTS` (safety valve), else `"agent"` — the retry loop. The `attempts` counter lives in a `State(MessagesState)` subclass.

- **Error anchor — `.content` isn't always a string:**
  ```text
  AttributeError: 'list' object has no attribute 'strip'
  ```
  - The only `.strip()` was `judge_result.content.strip().upper()`; the model returned `.content` as a **list of content blocks**, not `"Y"`/`"N"`.
  - Fix (helper that normalizes both shapes before `.strip()`):
    ```python
    def _as_text(content) -> str:
        if isinstance(content, str):
            return content
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    ```
  - Predicted: `.content` is `"Y"`. Actual: it was a list → crash. Reusable rule: **coerce `message.content` to text before string ops.**

- **Studio-usage insight:** running **"As Node: judge"** with hand-typed state (`attempts = -4`, `helpfulness = "What can you do"`) created confusing behavior (negative attempts, judge running twice). Clean test = new thread, real message in Messages, `Attempts = 0`, leave `Helpfulness` blank.

- **Subfolder anchor #1 — Vercel CLI from the wrong place:**
  ```text
  $ (in 09_Agent_Servers/frontend) vercel git connect
  Error: No local Git repository found.
  ```
  - Git was actually fine (`origin` = my fork); `vercel git connect` just expects to run at the **repo root**, and it's clumsy for a subfolder app.
  - Fix (not CLI): connect the repo in the **Vercel dashboard** and set **Root Directory = `09_Agent_Servers/frontend`**.

- **Subfolder anchor #2 — `azd pipeline config` half-succeeded:**
  ```text
  ERROR: check git push prevent: ... lstat .../09_Agent_Servers/.github/workflows: no such file or directory
  ```
  - `azd` created the workflow at the **repo root** `.github/workflows/` but (run from the subfolder) looked for it *under* `09_Agent_Servers/` for its final commit step. Everything real (MSI, federated creds, secrets, variables) succeeded; only the auto-commit failed.
  - Fix — make the workflow subfolder-aware and scope its trigger:
    ```yaml
    jobs:
      build:
        defaults:
          run:
            working-directory: 09_Agent_Servers   # so azd finds azure.yaml
    # on.push.paths: ['09_Agent_Servers/**', '.github/workflows/azure-dev.yml']
    ```
  - Reusable rule: **path-filter the trigger** so backend-only changes don't fire on every unrelated push, and set `working-directory` when the azd project isn't at the repo root.

- Next small experiment: force the loop to actually iterate — either ask something answered poorly, or temporarily make the judge stricter — and watch `attempts` climb toward `MAX_ATTEMPTS` in the Trace tab.

## Engineering Connection
- Where this appears in real AI systems: split deployment (stateless agent API + separate web UI), reflection / self-critique loops (LLM-as-judge with a retry cap), and secure key handling via a backend proxy.
- Tradeoffs:
  - Static generated Dockerfile (reproducible, azd-friendly) vs live manifest reading (convenient, but not how the prod image builds) → you inherit a **drift** failure mode.
  - Self-correction loop improves quality but multiplies latency + token cost per turn; `MAX_ATTEMPTS` bounds the blast radius.
  - Build-time `NEXT_PUBLIC_*` inlining (fast, CDN-cacheable) vs runtime config (more flexible) → forces a two-pass deploy.
- Failure modes seen this session:
  - `langgraph.json` and `Dockerfile` drift → new graph silently absent after a "successful" deploy.
  - Assuming default assistants appear for graphs added to an already-initialized DB.
  - `'list' object has no attribute 'strip'` from unnormalized `.content`.
  - Retry loop re-runs the agent on full history but never tells it *why* it's retrying → second attempt can look like the first.
  - (Frontend, from earlier) `Invalid URL` / `405` from a wrong or relative `NEXT_PUBLIC_API_URL`; Vercel Deployment Protection blocking public access.
- CI/CD tradeoffs: `azd pipeline config` (OIDC, secretless, one command) vs storing a service-principal secret → OIDC is safer (nothing long-lived to leak) but needs the federated-subject trust set up correctly.
- New failure mode: **monorepo subfolder mismatch** — CLI deploy tools assume the app is at the repo root; symptoms are "no repo found" (Vercel) or files written to the wrong dir (azd). Fix with Root Directory / `working-directory`.
- Cost/noise: without `paths:` filters, every push to `main` re-provisions Azure — wasteful. Scope triggers to the relevant subtree.
- Two-track deploy now in place: `frontend/**` → Vercel; `09_Agent_Servers/**` → GitHub Actions → `azd provision && azd deploy`.
- Evaluation/monitoring angle: log `attempts` and `helpfulness` per turn; a rising average `attempts` signals a degrading agent. Compare Studio Traces for helpful (1 attempt) vs unhelpful (multiple) runs — the Activity 1 deliverable.
- Security/cost/deployment: the browser calls only `NEXT_PUBLIC_API_URL=https://<app>.vercel.app/api`; the proxy (`route.ts`) injects `LANGGRAPH_API_URL` + `LANGSMITH_API_KEY` server-side so the Azure URL and key never reach the client (Homework Q2).

## Post-Task Teaching Debrief
- Approach taken: treated "graph not visible" as a pipeline question, not a code question. Confirmed the manifest was right, then used `curl` to isolate *where* the graph went missing (a 404 from `/assistants` proved it wasn't loaded), which pointed straight at the build. Then read `azure.yaml` → found it builds a static `Dockerfile` → found the frozen `LANGSERVE_GRAPHS`.
- Roads not taken: could have restarted the container hoping for auto-creation, or created the assistant by hand via `POST /assistants` — but both are band-aids that don't fix the drift; regenerating the Dockerfile fixes the actual source.
- How the pieces connect: `langgraph.json` (source) → `langgraph dockerfile` → `Dockerfile` (`LANGSERVE_GRAPHS`) → `azd deploy` builds/pushes image → Container App loads graphs → default assistants created → `/assistants/search` lists them → frontend/Studio target one by `assistantId` (`page.tsx` hardcodes `"simple_agent"`).
- Mistakes and dead ends: assuming `azd deploy` success = code live; assuming `.content` is a string; testing via "As Node" with hand-entered state which muddied the picture.
- Future pitfalls ("wish I'd known"): **any time you change graphs, regenerate the Dockerfile before deploying** — consider scripting `langgraph dockerfile Dockerfile && azd deploy` so it can't be forgotten. Also: verify the fix is actually committed/pushed (the terminal showed "nothing added to commit / Everything up-to-date" — worth a `git status` double-check).
- Expert lens: when something "isn't showing up" in a deployed system, bisect the pipeline with cheap probes (`curl`, logs) instead of re-reading code; the bug is often at a boundary (manifest↔image, source↔generated, client↔server). For LLM plumbing, never assume response shape — normalize `.content`.
- Transferable lessons: distinguish source-of-truth from generated artifacts; "deploy succeeded" ≠ "my change is running"; bound self-correcting loops; keep secrets behind a server proxy; give a retry loop feedback if you want the retry to differ.

## Reflect
- What I understand now:
  - Azure builds from a **static `Dockerfile`**, not from `langgraph.json`; the graph list is frozen in `ENV LANGSERVE_GRAPHS`. Regenerate with `uv run langgraph dockerfile Dockerfile`.
  - `/assistants/search` lists assistants (graph instances). A `graph 'X' not found` 404 means the *image* lacks the graph, not the manifest.
  - `simple_agent` and `agent_with_helpfulness` are independent graphs; `agent` + `judge` are cooperating nodes inside the loop.
  - `message.content` may be a `str` or a `list` of blocks — normalize before string ops.
  - `NEXT_PUBLIC_API_URL` is baked at build time → two-pass Vercel deploy; secrets stay in the server-side proxy.
- What was unclear / corrected:
  - Misconception: "Edit `langgraph.json` + `azd deploy` = new graph live." → Corrected: must regenerate the Dockerfile first.
  - Misconception: "`azd deploy` SUCCESS means my code runs." → Corrected: verify with `/assistants/search`.
  - Misconception: "The two dropdown graphs work together." → Corrected: independent; only the inner nodes cooperate.
  - Misconception: "`.content` is always a string." → Corrected: can be a list of content blocks.
- One-minute explanation: I deployed a LangGraph agent as a hosted API on Azure Container Apps and a Next.js UI on Vercel. My new `agent_with_helpfulness` graph didn't show up even after a successful deploy because Azure builds from a generated `Dockerfile` whose `LANGSERVE_GRAPHS` had drifted from `langgraph.json`; regenerating it fixed that. The graph is an agent→judge→retry loop bounded by `MAX_ATTEMPTS`. A `'list' object has no attribute 'strip'` crash taught me that an LLM message's `.content` can be a list, so I normalize it to text before parsing "Y"/"N". The frontend stays secure by talking only to its own `/api` proxy, which injects the Azure URL and key server-side.
- Active recall questions:
  1. Why did the new graph stay invisible even though `azd deploy` said SUCCESS?
  2. Where is the graph list actually frozen for the Azure image, and how do you refresh it?
  3. What's the difference between a graph, an assistant, and a thread?
  4. Are `simple_agent` and `agent_with_helpfulness` cooperating? What about `agent` and `judge`?
  5. What does `route` return, and what are the two ways the loop ends?
  6. Why did `.strip()` throw `'list' object has no attribute 'strip'`, and how do you fix it generally?
  7. Why must `NEXT_PUBLIC_API_URL` be set before the Vercel build, and why an absolute URL?
  8. How does the frontend avoid exposing the Azure URL and API key to the browser?
  9. Why won't a good agent visibly "loop," and how would you force it to for a demo?
  10. If you wanted each retry to genuinely improve, what would you add before re-running the agent?
  11. Why did `vercel git connect` say "No local Git repository found" when git was clearly working?
  12. What does OIDC federated identity buy you over storing an Azure secret in GitHub?
  13. Difference between a GitHub Actions *secret* and a *variable*?
  14. Which two workflow edits make an azd pipeline work for an app in a subfolder?
- Spaced review suggestion: re-answer the drift + `/assistants/search` questions tomorrow; re-derive the loop wiring (edges + `route`) from memory in 3 days; revisit the Vercel proxy/env-var security model next week.
