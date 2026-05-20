from __future__ import annotations

from pathlib import Path

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.writer import write_outputs


def test_write_outputs_basic(tmp_path: Path) -> None:
    """Test writing only the summary file."""
    config = LlmsTxtConfig(root=tmp_path, output_dir="out")
    summary_content = "Summary content"

    written = write_outputs(config, summary_content, full=None)

    out_dir = tmp_path / "out"
    summary_path = out_dir / "llms.txt"

    assert summary_path.exists()
    assert summary_path.read_text(encoding="utf-8") == summary_content
    assert (out_dir / "llms-full.txt").exists() is False
    assert written == [summary_path]


def test_write_outputs_full(tmp_path: Path) -> None:
    """Test writing both summary and full files."""
    config = LlmsTxtConfig(root=tmp_path, output_dir="out")
    summary_content = "Summary content"
    full_content = "Full content"

    written = write_outputs(config, summary_content, full_content)

    out_dir = tmp_path / "out"
    summary_path = out_dir / "llms.txt"
    full_path = out_dir / "llms-full.txt"

    assert summary_path.exists()
    assert summary_path.read_text(encoding="utf-8") == summary_content
    assert full_path.exists()
    assert full_path.read_text(encoding="utf-8") == full_content
    assert written == [summary_path, full_path]


def test_write_outputs_creates_dir(tmp_path: Path) -> None:
    """Test that the output directory is created if it doesn't exist."""
    nested_out_dir = "some/nested/output"
    config = LlmsTxtConfig(root=tmp_path, output_dir=nested_out_dir)

    write_outputs(config, "summary", None)

    assert (tmp_path / nested_out_dir).is_dir()


def test_write_outputs_custom_filenames(tmp_path: Path) -> None:
    """Test that custom filenames from config are respected."""
    config = LlmsTxtConfig(
        root=tmp_path,
        output_summary="custom.txt",
        output_full="custom-full.txt"
    )

    written = write_outputs(config, "summary", "full")

    assert (tmp_path / "custom.txt").exists()
    assert (tmp_path / "custom-full.txt").exists()
    assert written == [tmp_path / "custom.txt", tmp_path / "custom-full.txt"]
