<p align = "center" draggable="false" ><img src="https://github.com/AI-Maker-Space/LLM-Dev-101/assets/37101144/d1343317-fa2f-41e1-8af1-1dbb18399719"
     width="200px"
     height="auto"/>
</p>

<h1 align="center" id="heading">Session 11: Claude Code & the Claude Agent SDK</h1>

| 📰 Session Sheet | ⏺️ Recording | 🖼️ Slides | 👨‍💻 Repo | 📝 Homework | 📁 Feedback |
|:-----------------|:-------------|:----------|:----------|:------------|:------------|
| [Session 11: Claude Code & Claude Agent SDK ](https://github.com/AI-Maker-Space/The-AI-Engineering-Certification-v1.0/tree/main/00_Docs/Modules/11_Claude_Code) |[Recording!](https://us02web.zoom.us/rec/share/2I5HA6DwVFgmtyjPaq1SJDgkaVEuYZoWYyMCK8DOAZ99Zm6f7dTi0IGONXj6mRel.YHFzKF03mI5v6JAM) <br> passcode: `&Qhi!cf0`| [Session 11 Slides](https://canva.link/uw1cl42x84tm6zh) |You are here! <br><br> [Certification Challenge](https://github.com/AI-Maker-Space/The-AI-Engineering-Certification-v1.0/tree/main/00_Docs/Certification%20Challenge) | [Optional Session 11 Assignment](https://forms.gle/sAyr5BgBLTfgJV8EA) <br><br>  [Cert Challenge Submission Form](https://forms.gle/xtM9F38nfRKcdjH97)| [Feedback 7/7](https://forms.gle/oDrguLDNvva65mtM8) |

## Useful Resources

**Claude Code**
- [Claude Code Documentation](https://code.claude.com/docs) — official docs: setup, workflows, settings
- [Claude Code Quickstart](https://code.claude.com/docs/en/quickstart) — from install to first session
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices) — Anthropic engineering guide

**Claude Agent SDK**
- [Agent SDK Overview](https://docs.anthropic.com/en/api/agent-sdk/overview) — what the SDK is and when to use it
- [Building Agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) — Anthropic engineering deep dive

## Main Assignment

**Build a chat web app powered by the Claude Agent SDK** — and build it *with* Claude Code.

This session is markdown-only on purpose. There is no starter code and no notebook: every line of code in your final app will be written in collaboration with Claude Code. The session has one build arc across a single breakout room:

```text
you → Claude Code → chat app skeleton → wire in Agent SDK query()
      (FastAPI + chat UI, echo stub)      ├─ tools: Read / Glob / Grep
                                           └─ your custom tool
```

The finished product: a **codebase concierge** — a chat interface in the browser where an agent (with real tools) answers questions about any repository you point it at. In Session 10 you served models behind endpoints; today you serve an *agent* behind one.

Work through the three guides in order:

```text
01_Installing_Claude_Code.md   # install, authenticate, verify
02_Using_Claude_Code.md        # drive Claude Code; scaffold the chat app skeleton
03_Claude_Agent_SDK.md         # add the agent and connect it to your website
```

## Outline

### Breakout Room #1: Claude Code, the Agent SDK, and the Connection

- Task 1: Install Claude Code and authenticate ([guide](./01_Installing_Claude_Code.md))
- Task 2: Learn the loop — explore a repo you didn't write ([guide](./02_Using_Claude_Code.md))
- Task 3: Scaffold the chat app skeleton with Claude Code (plan → implement → verify)
- Task 4: Write the project's `CLAUDE.md`
- Question #1 and Question #2
- Task 5: Install the Agent SDK and run your first `query()` ([guide](./03_Claude_Agent_SDK.md))
- Task 6: Wire the agent into `/api/chat` — replace the echo stub
- Task 7: Conversation memory — resume sessions across messages
- Task 8: Give the agent a custom tool
- Question #3 and Question #4
- Activity #1: Level Up the Chat App

## Questions

### ❓ Question #1

While scaffolding in Task 3 you used **plan mode** before letting Claude Code write anything. Why does an agent that can execute shell commands need a permission system at all, and why is plan mode particularly valuable when starting a project from an empty directory?

#### ✅ Answer

Because an agent *acts* rather than suggests. A chat model's worst output is wrong text I can ignore; an agent's worst output is a real side effect on a real filesystem, executed with my privileges. The model is probabilistic, but `rm` is not reversible. A permission system inserts a human at exactly the moments that can't be undone, which converts "discover the mistake afterwards" into "veto it beforehand."

Plan mode matters most from an empty directory because there is nothing to constrain the agent and nothing to correct it against. In an existing repo, conventions are legible in the code and a bad change shows up as a diff against something that worked. From empty, every decision is unconstrained — dependency manager, framework, file layout, where the reply logic lives — and each one becomes load-bearing for everything built afterwards. The cost curve is steepest at the start: agreeing "the stub is isolated in one swappable function" costs one sentence in a plan, and a refactor if discovered later.

My own build proves the point. The plan for the skeleton specified an `async` `generate_reply` that accepts an unused `conversation_id`. Both looked like over-engineering for an echo stub. Because they were agreed up front, wiring in the real agent (Task 6) was a change to one function body, and conversation memory (Task 7) needed no signature change at all.

Plan mode has a second benefit I didn't expect: it makes reasoning checkable. My Task 8 plan claimed a custom tool would reduce turns and cost. Because the claim was written down, I measured it — and it was wrong (identical turn count, higher cost). Stated in a plan, a bad assumption gets tested. Buried in code, it just becomes folklore.

### ❓ Question #2

`CLAUDE.md` is loaded into context at the start of every session. What belongs in it — and what *doesn't*? How does this relate to what you learned about context management and memory in Session 3?

#### ✅ Answer

What belongs is everything a fresh session cannot derive by reading the code: how to run and test the thing, the one architectural decision that matters, why deliberately odd-looking code is deliberate, and facts that were expensive to learn and contradict expectations. What doesn't belong is anything a `Read` would reveal, long prose, aspirations, and anything that has quietly become false.

I saw the payoff immediately. My very first `query()` against the project answered "what does this project do?" accurately with **zero tool calls** — the reply was essentially a paraphrase of my `CLAUDE.md`, which the harness had already loaded. A good `CLAUDE.md` doesn't just inform the agent, it removes work: no glob, no reads, fewer turns, less money.

The load-bearing notes earned their place too. My file explained that `generate_reply` was `async` despite echoing needing no `await`, and that `conversation_id` was intentionally unused. Without that, the obvious "cleanup" would have deleted exactly the hooks the SDK needed.

The failure mode is staleness, and I hit it repeatedly. My file described wiring in the agent as future work minutes after the agent was wired in. The UI header still announced "Echo stub" while a live agent answered questions beneath it. Every line is a liability that has to be maintained, which is the real argument for keeping it short.

The sharpest lesson: **a convention the code visibly violates is worse than no convention.** Mine said replies contain no markdown, while replies were shipping bullet lists. That doesn't just fail — it teaches the next reader to distrust the whole file.

This is Session 3's finite-context problem from the other end. `/compact` reclaims context *after* it fills; `CLAUDE.md` is a tax paid *before* anything starts, on every future session forever. Both are the same decision — what's worth keeping versus rediscovering — and the same tradeoff I made building summarization middleware. The difference is that summarization decays automatically while `CLAUDE.md` decays silently, so pruning has to be deliberate.

### ❓ Question #3

The Agent SDK gives you the same agent loop that powers Claude Code. Compare this to the agent loops you hand-built with LangGraph in Sessions 2–4: what does the SDK give you for free, and what control do you give up?

#### ✅ Answer

**Free:** the loop itself, production file and search tools, retries, context compaction, MCP client support, and session persistence. The scale of that last one is easy to miss. Conversation memory (Task 7) was about ten lines — a dict mapping my `conversation_id` to the SDK's `session_id`. I never stored a single message. The harness keeps transcripts on disk; I keep a 36-character ticket stub. In LangGraph I'd have built a checkpointer, chosen a store, and serialized state myself.

**Given up:** model provider choice, arbitrary graph topologies — and one cost I didn't anticipate, which turned out to be the expensive one.

**I gave up legibility of the control surface.** In a hand-built loop, the tools the model has are the tools I passed it; I can read the dispatch code and know. With the SDK I couldn't, and the documentation actively misled me:

- `allowed_tools` reads like a whitelist. It isn't — it's an auto-approve list. With `allowed_tools=["Read","Glob","Grep"]` the agent successfully ran `Bash`.
- `permission_mode="dontAsk"` documents itself as denying anything not pre-approved. It didn't.
- `can_use_tool` raises at runtime unless the prompt is an async iterable — a constraint invisible until you try it.
- The set of tools offered changed depending on an environment variable, so a one-off enumeration was already wrong.

Four documented mechanisms, one of which (`disallowed_tools`) actually worked, and the only way to find out was empirical probing. That's the real trade: the SDK's loop is battle-tested, but its behavior is something I *test for* rather than *read*. A hand-built loop is more work and less capable, and I would have known exactly what it could do.

The other structural difference: **defaults run opposite directions.** A LangGraph loop starts with zero tools and I add what's needed. The SDK starts by offering 25+ — `Bash`, `Write`, `Workflow`, `CronCreate`, `WebFetch` — and expects me to subtract. Additive defaults fail closed; subtractive defaults fail open.

### ❓ Question #4

Your chat app could have called a chat completions API directly, the way you did early in the course. What do you gain by routing every message through the Agent SDK's `query()` instead — and what new risks does an agent with tools introduce that a plain chat completion doesn't have? How did your tool allowlist and permission mode address them?

#### ✅ Answer

**What I gain:** a completion can only discuss a repository I already put in the prompt. `query()` gets an agent that assembles its own context — globbing the tree, grepping for entry points, reading what looks relevant, iterating until it can answer. I never told it which files to read. Answering "what's the largest file in `app/`?" over an arbitrary repo isn't a prompt-engineering problem; it needs a loop with real tools.

**What's new:** side effects. A completion's worst case is confidently wrong text. An agent's tool calls hit a real filesystem with the server's privileges, steered by untrusted input from a public textbox. Two distinct risks: **exfiltration** — reading anything reachable and printing it into a chat reply — and **mutation or execution**.

**How my controls addressed them — including where I was wrong.**

I began with `allowed_tools=["Read","Glob","Grep"]`, `cwd`, and `max_turns=25`, and wrote in my `CLAUDE.md` that the agent "structurally cannot modify anything." Then I tested it, and that was false.

With exactly that configuration the agent ran `Bash`. I confirmed it with a command whose output it couldn't fabricate (`openssl rand -hex 12`) and watched the hex string come back. `permission_mode="dontAsk"` didn't stop it either. My earlier "proof" of read-only — the agent politely declining to delete `README.md` — proved nothing: that refusal came from `system_prompt` personality, not absent capability. **An agent's refusal is evidence about its manners, not its permissions.**

What actually works is `disallowed_tools`: those tools are never offered to the model at all. Verified — `Bash` absent from the init message's tool list, no tool calls attempted, no output produced.

Two further findings:

1. **`cwd` does not sandbox custom tools.** It confines the built-ins, but my `repo_stats` tool is ordinary Python in my own process, so the SDK cannot restrain it. Handed `path="../.."` it would have walked straight out of the repo. It resolves paths first and then requires containment in `TARGET_REPO`; `..`, absolute paths, and escaping symlinks are all refused. Every custom tool is a potential hole in your own sandbox.
2. **Blocklists rot faster than you'd think.** I enumerated the toolset and denied everything unnecessary — then a runtime warning I'd added caught `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` on the first real run, because the shell I enumerated in had `CLAUDE_CODE_ENABLE_TASKS=0`. Not an SDK upgrade. A different terminal.

**Residual risk I'm accepting:** the agent can still read anything inside `TARGET_REPO`, including a committed `.env`. `cwd` is the only scope, and for a localhost project that's a reasonable call — but it's a decision, not a guarantee.

The lesson worth more than the code: the boundary I could *describe* was not the boundary that *existed*, and nothing short of probing distinguished them.

## Activity 1: Level Up the Chat App

Extend your working chat app with **at least one** of the following (built with Claude Code, of course):

1. **Live progress streaming** — stream the agent's activity to the browser (e.g. via Server-Sent Events) so users see tool calls ("reading `app.py`…") while the agent works, instead of a spinner
2. **Multi-conversation support** — a sidebar of separate conversations, each mapped to its own SDK session
3. **A second custom tool** — something genuinely useful for your target repo (e.g. `git_log` for recent changes, or a test-runner summary tool)

Whichever you pick, demo it in your Loom video and explain the design decision in one paragraph.

## Advanced Activity: The Cat Shop Concierge

Connect your Session 8 cat shop MCP server to your chat app's agent via the SDK's `mcp_servers` option. Your chat app becomes a shopping concierge: users can browse the catalog, fill a cart, and check out — in natural language, through the UI you built, hitting the OAuth-protected server you wrote in Session 8.

Include your findings and a demo in your Loom video.

## Ship 🚢

The working chat app!

### Deliverables

- A short Loom showing:
  - Claude Code scaffolding or extending the app (plan → implement → verify — show the plan!); and
  - the chat app answering real questions about a repository, including at least one visible custom-tool use

## Share 🚀

Make a social media post about your final application!

### Deliverables

- Make a post on any social media platform about what you built!

Here's a template to get you started:

```
🚀 Exciting News! 🚀

I am thrilled to announce that I have just built and shipped a chat app powered by the Claude Agent SDK — scaffolded entirely with Claude Code! 🎉🤖

🔍 Three Key Takeaways:
1️⃣
2️⃣
3️⃣

Let's continue pushing the boundaries of what's possible in the world of AI agents. Here's to many more innovations! 🚀
Shout out to @AIMakerspace !

#ClaudeCode #AgentSDK #AIAgents #Innovation #AI #TechMilestone

Feel free to reach out if you're curious or would like to collaborate on similar projects! 🤝🔥
```

## Submitting Your Homework (Optional For Extra Mark)

Follow these steps to prepare and submit your homework:

1. Pull the latest updates from upstream into the main branch of your repo:

```bash
git checkout main
git pull upstream main
git push origin main
```

2. Work through `01_Installing_Claude_Code.md`, `02_Using_Claude_Code.md`, and `03_Claude_Agent_SDK.md` in order.
3. Build your chat app in a new `chat-app/` folder inside this session directory (include its `CLAUDE.md` — we want to see it!).
4. Fill in your answers to Questions #1–#4 in this README.
5. Complete Activity #1 and record your Loom video.
6. Add, commit, and push your work to your origin repository. Remove `.env` files and API keys before committing.

When submitting your homework, provide the GitHub URL to your repo.
