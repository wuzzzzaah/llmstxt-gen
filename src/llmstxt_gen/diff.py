"""Git diff helper for llmstxt-gen."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when git is unavailable or returns an error."""


def get_changed_files(ref: str, root: Path) -> set[str]:
    """Return the set of files changed since ``ref`` relative to ``root``.

    Uses ``git diff --name-only <ref>`` to find changed files.
    """
    try:
        # We use --relative to get paths relative to the current directory if we are in a subdir,
        # but the prompt says we should use 'git diff --name-only'.
        # If 'root' is the repo root, 'git diff --name-only' will return paths relative to repo root.
        result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise GitError("git command not found") from None

    if result.returncode != 0:
        raise GitError(f"git diff failed: {result.stderr.strip()}")

    changed = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            changed.add(line)

    return changed
