"""The chat brain: a Claude Agent SDK codebase concierge.

Everything else in the app talks to `generate_reply` and nothing else, so this is
the only module that knows an agent exists at all.
"""

import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage, query
from claude_agent_sdk.types import StreamEvent

from app.config import target_repo
from app.tools import CONCIERGE

logger = logging.getLogger(__name__)

# The tools this concierge is meant to have. Read-only by construction.
#
# IMPORTANT: `allowed_tools` alone does NOT restrict anything. It is an auto-approve
# list — tools left off it stay available to the model and, headless with no permission
# callback, run unchallenged. Measured, not assumed: with exactly this list and no gate,
# the agent successfully ran `Bash` with `echo`. The `_gate` callback below is what
# actually makes the list a boundary.
ALLOWED_TOOLS = ["Read", "Glob", "Grep"]

# Custom tools are allowlisted exactly like built-ins, under
# mcp__<server key>__<tool name>. Without this entry the agent can see repo_stats
# in its tool list but never gets permission to call it.
CUSTOM_TOOLS = ["mcp__concierge__repo_stats"]

# ToolSearch is permitted on purpose: Glob and Grep are *deferred* tools that are not
# offered up front, and ToolSearch is how the agent loads their schemas. Deny it and
# searching quietly stops working.
INFRASTRUCTURE_TOOLS = ["ToolSearch"]

PERMITTED_TOOLS = frozenset(ALLOWED_TOOLS + CUSTOM_TOOLS + INFRASTRUCTURE_TOOLS)

# The list that actually enforces read-only. Everything the runtime offers by default,
# minus what we permit above. Measured, not guessed: this is the `tools` array from the
# init SystemMessage on claude-agent-sdk 0.2.128.
#
# A blocklist rots — a tool added in a future SDK version would be permitted by default
# — so `_warn_about_unknown_tools` below flags anything we have not classified.
DENIED_TOOLS = [
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "Task",
    "Workflow",
    "Skill",
    "TodoWrite",
    "CronCreate",
    "CronDelete",
    "CronList",
    "DesignSync",
    "EnterWorktree",
    "ExitWorktree",
    "Monitor",
    "PushNotification",
    "ReportFindings",
    "ScheduleWakeup",
    "SendMessage",
    "TaskOutput",
    "TaskStop",
    # Added after `_warn_about_unknown_tools` flagged these at runtime. They were absent
    # from the enumeration run because that shell had CLAUDE_CODE_ENABLE_TASKS=0 set —
    # the offered toolset varies with the environment, so the warning is the only
    # reliable way to discover the full set. Deny by default: a codebase concierge has
    # no business managing tasks.
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
]


def _warn_about_unknown_tools(message: SystemMessage) -> None:
    """Log any offered tool we neither permitted nor denied.

    The guard against a stale blocklist: if a future SDK ships a new tool, this is how
    you find out, rather than discovering it in an incident.
    """
    offered = set((getattr(message, "data", None) or {}).get("tools") or [])
    unclassified = offered - PERMITTED_TOOLS - set(DENIED_TOOLS)
    if unclassified:
        logger.warning(
            "Unclassified tools offered to the agent (review DENIED_TOOLS): %s",
            sorted(unclassified),
        )

# Hard cap on observe-then-decide round trips. A runaway agent does not hang, it bills.
MAX_TURNS = 25

# Pinned deliberately. Left unset, the SDK inherits whatever the ambient Claude Code
# runtime happens to default to — here that resolved to Opus with a 1M context window,
# so the same code would behave differently on another machine. Reproducibility is the
# main reason; cost is secondary and smaller than you'd guess (measured: $0.135 -> $0.109
# for a one-word answer, because ~21.5k cache-creation tokens per fresh session dominate
# regardless of model — that is Task 7's problem, not this constant's). Override with
# AGENT_MODEL for a question that genuinely warrants more.
DEFAULT_MODEL = "claude-sonnet-5"

# static/app.js renders replies with textContent, so markdown arrives as literal
# `**` and `|` clutter. Asking for prose costs one paragraph here; rendering
# markdown instead would mean injecting model output into the DOM.
SYSTEM_PROMPT = """You are a codebase concierge for the repository in your working directory.

Answer questions about that codebase by reading it. Be concise — a few sentences \
unless more is genuinely warranted. Cite the file paths you based your answer on \
inline, like app/main.py or app/models.py:12.

You have a repo_stats tool that returns a file inventory with line counts in one call. \
Use it for anything about file sizes, the largest or smallest file, or how many files a \
directory holds, instead of globbing and reading files one by one.

Write in plain prose. Do not use markdown: no headings, bold, bullet lists, tables, \
or backticks. The chat UI displays your reply as raw text, so markdown syntax shows \
up as noise rather than formatting."""

FALLBACK = "I couldn't put together an answer to that. Could you rephrase it?"

# One browser conversation -> the SDK session holding its history. The harness stores
# the actual transcript; this only remembers which session belongs to whom.
#
# In-memory and process-local, so it empties on restart (including every --reload) and
# would not survive more than one worker. That is the honest limit of today's memory
# story, not an oversight.
_SESSIONS: dict[str, str] = {}


@dataclass(frozen=True)
class Reply:
    """What `generate_reply` hands back.

    `resumed` says whether this answer continued an existing SDK session. The browser
    keeps conversation history in localStorage while `_SESSIONS` lives in memory here, so
    the two can disagree after a restart — a sidebar full of history in front of an agent
    that remembers none of it. `resumed=False` on a conversation the browser thinks is
    ongoing is how the UI detects that instead of silently looking broken.
    """

    text: str
    resumed: bool


@dataclass(frozen=True)
class StreamChunk:
    """One progress event on the way to an answer.

    `event` is one of "thinking", "tool", "text", "error", "done". A stream always ends
    with exactly one "done", whose `reply` is the authoritative answer — accumulated
    "text" deltas are a preview to render, not the record.

    There is deliberately no "tool finished" event. Measured against the real stream, tool
    execution here takes ~20ms while the gaps *between* tools take 1.5-2s of model
    inference — so a label that appeared and cleared on tool boundaries would flash for a
    frame and then leave the user watching nothing during the actual wait. The UI keeps a
    running list of tools that have run and shows "thinking" text in the gaps instead.

    Deliberately not SSE-shaped: `app.main` owns the wire format, this module owns replies.
    """

    event: str
    data: dict


# Plumbing, not progress. ToolSearch is how the runtime loads the deferred Glob/Grep
# schemas; announcing it to a user reads as a mystery step in the middle of their answer.
HIDDEN_TOOLS = {"ToolSearch"}


def _tool_label(name: str) -> str:
    """Human-facing tool name: `mcp__concierge__repo_stats` -> `repo_stats`."""
    return name.rsplit("__", 1)[-1] if name.startswith("mcp__") else name


def _options(target: Path, resume: str | None) -> ClaudeAgentOptions:
    """Build options fresh per request.

    Per-request rather than once at import so TARGET_REPO is read at request time and
    each call can carry its own `resume` session.
    """
    return ClaudeAgentOptions(
        model=os.environ.get("AGENT_MODEL") or DEFAULT_MODEL,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"concierge": CONCIERGE},
        allowed_tools=[*ALLOWED_TOOLS, *CUSTOM_TOOLS],
        disallowed_tools=DENIED_TOOLS,
        cwd=str(target),
        max_turns=MAX_TURNS,
        resume=resume,
        # Yields extra StreamEvent messages carrying raw API events, so we can report
        # thinking, tool calls, and text as they happen. The buffered path ignores them.
        include_partial_messages=True,
        # display defaults to "omitted", which streams thinking blocks with empty text.
        # "summarized" is what makes the reasoning actually readable — and it is the only
        # thing that fills the multi-second gaps between tool calls.
        thinking={"type": "adaptive", "display": "summarized"},
    )


async def stream_reply(
    message: str, conversation_id: str
) -> AsyncIterator[StreamChunk]:
    """Answer `message`, reporting progress as it happens.

    The only place `query()` is called — `generate_reply` wraps this — so the streaming
    and buffered endpoints cannot drift apart.

    Replies are conversational: `conversation_id` selects the SDK session to resume, so
    follow-up questions can refer back to earlier ones. The first message of a
    conversation resumes nothing and starts a new session.
    """
    resumed_session = _SESSIONS.get(conversation_id)
    resumed = resumed_session is not None

    target = target_repo()
    if not target.is_dir():
        logger.error("TARGET_REPO is not a directory: %s", target)
        text = (
            "I'm not configured correctly — the repository I'm supposed to read "
            "doesn't exist. Check the TARGET_REPO environment variable."
        )
        yield StreamChunk("error", {"message": text})
        yield StreamChunk("done", {"reply": text, "resumed": resumed})
        return

    options = _options(target, resume=resumed_session)

    # A tool's *input* also streams, as input_json_delta, and text must not be forwarded
    # while any tool block is open or raw JSON fragments land in the message bubble.
    #
    # A counter, not a boolean: the model emits parallel tool calls, so two tool_use
    # blocks can be open at once and the first content_block_stop must not clear
    # suppression while the second is still streaming its input.
    open_tool_blocks = 0

    try:
        async for msg in query(prompt=message, options=options):
            if isinstance(msg, SystemMessage) and getattr(msg, "subtype", "") == "init":
                _warn_about_unknown_tools(msg)

            elif isinstance(msg, StreamEvent):
                event = msg.event
                kind = event.get("type")

                if kind == "content_block_start":
                    block = event.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        open_tool_blocks += 1
                        name = block.get("name") or ""
                        if name not in HIDDEN_TOOLS:
                            yield StreamChunk("tool", {"name": _tool_label(name)})

                elif kind == "content_block_delta":
                    delta = event.get("delta") or {}
                    delta_type = delta.get("type")

                    if delta_type == "thinking_delta":
                        thought = delta.get("thinking") or ""
                        if thought:
                            yield StreamChunk("thinking", {"delta": thought})
                    elif delta_type == "text_delta" and not open_tool_blocks:
                        text = delta.get("text") or ""
                        if text:
                            yield StreamChunk("text", {"delta": text})

                elif kind == "content_block_stop" and open_tool_blocks:
                    open_tool_blocks -= 1

            elif isinstance(msg, ResultMessage):
                # Remember the session so the next message in this conversation
                # continues it. Taken from ResultMessage rather than the init
                # SystemMessage because it is the message we already handle, and
                # re-reading it every turn keeps the mapping right even if resuming
                # mints a fresh session id.
                if msg.session_id:
                    _SESSIONS[conversation_id] = msg.session_id
                yield StreamChunk(
                    "done", {"reply": msg.result or FALLBACK, "resumed": resumed}
                )
                return
    except Exception:
        # Broad on purpose: anything that escapes here would abort the stream mid-frame,
        # which the frontend can only render as a generic failure. A sentence inside the
        # conversation is friendlier, and the traceback is still logged.
        logger.exception("Agent failed while answering: %r", message)
        text = "Something went wrong while I was reading the code. Please try again."
        yield StreamChunk("error", {"message": text})
        yield StreamChunk("done", {"reply": text, "resumed": resumed})
        return

    # Stream finished without ever yielding a ResultMessage (max_turns exhausted, say).
    logger.warning("Stream ended with no ResultMessage for: %r", message)
    yield StreamChunk("done", {"reply": FALLBACK, "resumed": resumed})


async def generate_reply(message: str, conversation_id: str) -> Reply:
    """Buffered answer: run the agent to completion and return just the final reply.

    A thin wrapper over `stream_reply` so `POST /api/chat` keeps working for curl and
    smoke tests without a second copy of the agent plumbing.
    """
    reply = Reply(FALLBACK, False)
    async for chunk in stream_reply(message, conversation_id):
        if chunk.event == "done":
            reply = Reply(chunk.data["reply"], chunk.data["resumed"])
    return reply
