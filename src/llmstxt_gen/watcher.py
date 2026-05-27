from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

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
