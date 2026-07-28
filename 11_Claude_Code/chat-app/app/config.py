"""Shared configuration.

Lives in its own module because both `app.chat` (which points the agent at the repo)
and `app.tools` (which must validate paths against that same repo) need it, and
`app.chat` imports `app.tools`.
"""

import os
from pathlib import Path

# Derived from this file's location rather than the process cwd, so it does not matter
# which directory uvicorn was launched from. Set TARGET_REPO to point elsewhere.
DEFAULT_TARGET_REPO = Path(__file__).resolve().parent.parent


def target_repo() -> Path:
    """Absolute path of the repository the concierge answers questions about."""
    return Path(os.environ.get("TARGET_REPO") or DEFAULT_TARGET_REPO).expanduser().resolve()
