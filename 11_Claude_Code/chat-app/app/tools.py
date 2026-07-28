"""Custom in-process tools for the concierge agent.

Exposed to the agent as an SDK MCP server: the same protocol as a networked MCP
server, but the transport is a Python function call — no ports, no subprocess.

SECURITY: `cwd` in ClaudeAgentOptions confines the built-in Read/Glob/Grep tools. It
does **not** confine anything in this file. These are ordinary functions running in the
FastAPI process with its privileges, so the SDK cannot sandbox them. Every path a tool
here accepts must be validated against `target_repo()` explicitly — otherwise the
read-only, repo-scoped boundary the rest of the app relies on is bypassed by asking for
`path="../.."`.
"""

import logging
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.config import target_repo

logger = logging.getLogger(__name__)

# Never interesting, sometimes enormous.
SKIP_DIRS = {
    ".venv",
    "venv",
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}

# Cap the listing so a large repo cannot flood the model's context.
MAX_ENTRIES = 50


def _text(body: str) -> dict:
    """Wrap a string in the content shape the SDK expects back from a tool."""
    return {"content": [{"type": "text", "text": body}]}


def _resolve_inside_repo(raw: str) -> Path:
    """Resolve `raw` against the target repo, refusing anything that escapes it.

    `resolve()` collapses `..` and follows symlinks *before* the check, so neither
    traversal nor a symlink pointing outside the repo gets through. An absolute `raw`
    replaces the root entirely under pathlib's `/` semantics, which the same check
    catches. A leading `~` is never expanded here, so it is treated as an ordinary
    (almost certainly nonexistent) directory name rather than the home directory.
    """
    root = target_repo()
    candidate = (root / raw) if raw else root
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{raw!r} is outside the repository")
    return resolved


def _count_lines(path: Path) -> int | None:
    """Line count, or None if the file is not readable UTF-8 text.

    Streams rather than reading the whole file, so a huge file costs no more memory
    than a small one.
    """
    total = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for _ in handle:
                total += 1
    except (UnicodeDecodeError, OSError):
        return None
    return total


@tool(
    "repo_stats",
    "Inventory of text files with their line counts, largest first. Prefer this over "
    "Glob plus repeated Read whenever the question is about file sizes, which file is "
    "biggest or smallest, how many files exist, or the overall shape of a directory — "
    "it answers all of those in a single call. Pass a repository-relative directory in "
    "`path` to scope the listing (for example 'app'), or omit it for the whole "
    "repository. Paths outside the repository are refused.",
    {"path": str},
)
async def repo_stats(args: dict) -> dict:
    """Line-count inventory for a directory in the repo, largest file first.

    The decorator's description above is what the model reads; this is for whoever
    maintains it.
    """
    raw = (args.get("path") or "").strip()

    try:
        base = _resolve_inside_repo(raw)
    except ValueError as exc:
        logger.warning("repo_stats refused out-of-repo path: %s", exc)
        return _text(
            f"Refused: {exc}. repo_stats only reports on files inside the target "
            "repository."
        )

    if not base.exists():
        return _text(f"No such path in the repository: {raw or '.'}")

    root = target_repo()
    if base.is_file():
        candidates = [base]
    else:
        candidates = [
            path
            for path in base.rglob("*")
            if path.is_file()
            and not any(part in SKIP_DIRS for part in path.relative_to(root).parts)
        ]

    counted: list[tuple[int, str]] = []
    skipped = 0
    for path in candidates:
        lines = _count_lines(path)
        if lines is None:
            skipped += 1
            continue
        counted.append((lines, path.relative_to(root).as_posix()))

    if not counted:
        return _text(f"No readable text files under {raw or 'the repository root'}.")

    counted.sort(reverse=True)
    shown = counted[:MAX_ENTRIES]
    total_lines = sum(lines for lines, _ in counted)

    logger.info("repo_stats(path=%r) -> %d files, %d lines", raw, len(counted), total_lines)

    summary = (
        f"{len(counted)} text files, {total_lines} lines total, "
        f"under {raw or 'the repository root'}"
    )
    if len(counted) > len(shown):
        # Say so explicitly: a silent cut reads as a complete inventory.
        summary += f" (showing only the {len(shown)} largest)"
    if skipped:
        summary += f"; {skipped} non-text file(s) skipped"

    listing = "\n".join(f"{name} — {lines} lines" for lines, name in shown)
    return _text(f"{summary}\n{listing}")


CONCIERGE = create_sdk_mcp_server(name="concierge", version="1.0.0", tools=[repo_stats])
