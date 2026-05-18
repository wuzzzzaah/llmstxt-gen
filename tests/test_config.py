from pathlib import Path

from llmstxt_gen.config import find_pyproject, load_config


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


def test_find_pyproject_walks_upward(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_pyproject(nested) == tmp_path / "pyproject.toml"


def test_find_pyproject_returns_none_when_missing(tmp_path: Path) -> None:
    assert find_pyproject(tmp_path) is None
