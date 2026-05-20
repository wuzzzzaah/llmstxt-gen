from pathlib import Path

from llmstxt_gen.config import DEFAULT_EXCLUDE, find_pyproject, load_config


def test_load_config_returns_defaults_when_no_pyproject(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg.name == tmp_path.name
    assert cfg.max_tokens_summary == 8000
    assert cfg.include_private is False


def test_load_config_reads_tool_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
description = "A demo"

[tool.llmstxt_gen]
include = ["src/"]
exclude = ["tests/"]
include_private = true
max_tokens_summary = 1234
languages = ["python"]
""".strip()
    )
    cfg = load_config(tmp_path)
    assert cfg.name == "demo"
    assert cfg.description == "A demo"
    assert cfg.include == ["src/"]
    assert cfg.exclude == ["tests/"]
    assert cfg.include_private is True
    assert cfg.max_tokens_summary == 1234


def test_default_exclude_contains_test_patterns(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert "**/*.test.ts" in cfg.exclude
    assert "**/*.spec.ts" in cfg.exclude
    assert "**/*.test.py" in cfg.exclude
    assert "**/test_*.py" in cfg.exclude
    assert "**/__tests__/**" in cfg.exclude


def test_user_exclude_replaces_defaults(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.llmstxt_gen]\nexclude = []\n")
    cfg = load_config(tmp_path)
    assert cfg.exclude == []


def test_default_exclude_is_populated() -> None:
    assert len(DEFAULT_EXCLUDE) > 0
    assert all(isinstance(p, str) for p in DEFAULT_EXCLUDE)


def test_find_pyproject_walks_upward(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_pyproject(nested) == tmp_path / "pyproject.toml"


def test_find_pyproject_returns_none_when_missing(tmp_path: Path) -> None:
    assert find_pyproject(tmp_path) is None
