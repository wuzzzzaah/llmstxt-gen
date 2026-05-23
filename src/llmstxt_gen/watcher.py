from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from watchfiles.main import FileChange

try:
    from watchfiles import watch
except ImportError:
    watch = None


def iter_changes(root: Path) -> Iterator[set[str]]:
    """Yield on each batch of file changes under root."""
    if watch is None:
        raise ImportError(
            "The 'watchfiles' package is required for watch mode. "
            "Install it with: pip install llmstxt-gen[watch]"
        )

    for changes in watch(root):
        # changes is a set of tuples (ChangeType, path)
        yield {str(Path(c[1]).relative_to(root)) for c in changes}
