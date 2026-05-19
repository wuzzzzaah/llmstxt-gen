"""File system walker.

Walks a project directory yielding source files in supported languages,
honoring ``.gitignore`` and the user's configured ``exclude`` patterns.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pathspec

from llmstxt_gen.config import LlmsTxtConfig

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".cs": "csharp",
    ".scala": "scala",
    ".sc": "scala",
}

ALWAYS_EXCLUDED = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
}


@dataclass
class SourceFile:
    """A single source file ready to be parsed."""

    path: Path
    language: str
    content: str


def detect_language(path: Path) -> str | None:
    """Return the language name for a file path, or ``None`` if unsupported."""
    return EXTENSION_TO_LANGUAGE.get(path.suffix.lower())


def _load_gitignore(root: Path) -> pathspec.PathSpec[pathspec.Pattern]:
    gi = root / ".gitignore"
    if gi.is_file():
        return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text().splitlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", [])


def _matches_exclude(rel_str: str, exclude_spec: pathspec.PathSpec[pathspec.Pattern]) -> bool:
    return exclude_spec.match_file(rel_str) or exclude_spec.match_file(rel_str + "/")


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(2048)
    except OSError:
        return True
    return b"\x00" in chunk


def walk_repository(config: LlmsTxtConfig) -> Iterator[SourceFile]:
    """Yield :class:`SourceFile` objects for every supported file under ``config.root``.

    Files are skipped when they:

    - have an extension not in ``config.extensions``
    - sit under a directory in :data:`ALWAYS_EXCLUDED`
    - match a ``.gitignore`` rule at the repository root
    - match a user-specified ``exclude`` pattern
    - fall outside the user's ``include`` patterns when those are set
    - contain binary content
    """
    root = config.root.resolve()
    gitignore_spec = _load_gitignore(root)
    exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", config.exclude)
    include_spec = (
        pathspec.PathSpec.from_lines("gitwildmatch", config.include) if config.include else None
    )
    allowed_exts = {e.lower() for e in config.extensions}
    allowed_langs = set(config.languages)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ALWAYS_EXCLUDED for part in path.parts):
            continue
        if path.suffix.lower() not in allowed_exts:
            continue

        language = detect_language(path)
        if language is None:
            continue
        if language not in allowed_langs and not (
            language == "javascript" and "typescript" in allowed_langs
        ):
            continue

        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        rel_str = rel.as_posix()

        if gitignore_spec.match_file(rel_str):
            continue
        if _matches_exclude(rel_str, exclude_spec):
            continue
        if (
            include_spec is not None
            and not include_spec.match_file(rel_str)
            and not any(rel_str.startswith(p.rstrip("/") + "/") for p in config.include)
        ):
            continue
        if _is_binary(path):
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        yield SourceFile(path=path, language=language, content=content)
