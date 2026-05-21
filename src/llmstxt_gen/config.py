"""Configuration loading for llmstxt-gen.

Reads ``[tool.llmstxt_gen]`` from a project's ``pyproject.toml``. Every option has
a sensible default so a project with no configuration still produces useful
output.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".cs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
)
DEFAULT_LANGUAGES: tuple[str, ...] = (
    "python",
    "typescript",
    "go",
    "rust",
    "ruby",
    "java",
    "csharp",
    "cpp",
)
DEFAULT_EXCLUDE: tuple[str, ...] = (
    # Test files — rarely useful in agent context and produce empty sections
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/*.test.js",
    "**/*.test.jsx",
    "**/*.spec.ts",
    "**/*.spec.tsx",
    "**/*.spec.js",
    "**/*.spec.jsx",
    "**/*.test.py",
    "**/test_*.py",
    "**/__tests__/**",
    "**/tests/**",
    "**/test/**",
)


@dataclass
class LlmsTxtConfig:
    """Resolved configuration used by every stage of the pipeline."""

    name: str = ""
    description: str = ""
    version: str = ""
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    output_dir: str = "."
    output_summary: str = "llms.txt"
    output_full: str = "llms-full.txt"
    output_mini: str = "llms-mini.txt"
    cache_path: str = ".llmstxt_cache.json"
    include_private: bool = False
    max_tokens_summary: int = 8000
    max_tokens_full: int = 32000
    languages: list[str] = field(default_factory=lambda: list(DEFAULT_LANGUAGES))
    root: Path = field(default_factory=Path.cwd)


def find_pyproject(start: Path) -> Path | None:
    """Walk upward from ``start`` looking for a ``pyproject.toml`` file."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        path = candidate / "pyproject.toml"
        if path.is_file():
            return path
    return None


def load_config(root: Path, config_path: Path | None = None) -> LlmsTxtConfig:
    """Load a :class:`LlmsTxtConfig` for the project rooted at ``root``.

    If ``config_path`` is provided it is used directly. Otherwise the loader
    searches upward from ``root`` for a ``pyproject.toml``. A missing config
    file is not an error: defaults are returned with ``name`` set to the
    directory name.
    """
    root = root.resolve()
    pyproject = config_path if config_path is not None else find_pyproject(root)

    cfg = LlmsTxtConfig(name=root.name, root=root)
    if pyproject is None or not pyproject.is_file():
        return cfg

    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)

    project_table = data.get("project", {})
    if isinstance(project_table, dict):
        if "description" in project_table and isinstance(project_table["description"], str):
            cfg.description = project_table["description"]
        if "version" in project_table and isinstance(project_table["version"], str):
            cfg.version = project_table["version"]
        if "name" in project_table and isinstance(project_table["name"], str):
            cfg.name = project_table["name"]

    table = data.get("tool", {}).get("llmstxt_gen", {})
    if not isinstance(table, dict):
        return cfg

    for key in (
        "name",
        "description",
        "version",
        "output_dir",
        "output_summary",
        "output_full",
        "output_mini",
        "cache_path",
    ):
        if key in table and isinstance(table[key], str):
            setattr(cfg, key, table[key])

    for key in ("include", "exclude", "extensions", "languages"):
        if key in table and isinstance(table[key], list):
            setattr(cfg, key, [str(v) for v in table[key]])

    if "include_private" in table and isinstance(table["include_private"], bool):
        cfg.include_private = table["include_private"]

    for key in ("max_tokens_summary", "max_tokens_full"):
        if key in table and isinstance(table[key], int):
            setattr(cfg, key, table[key])

    return cfg
