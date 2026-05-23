"""Write rendered output to disk."""

from __future__ import annotations

from pathlib import Path

from llmstxt_gen.config import LlmsTxtConfig


def write_outputs(
    config: LlmsTxtConfig,
    summary: str | None = None,
    full: str | None = None,
    mini: str | None = None,
    diff: str | None = None,
) -> list[Path]:
    """Write rendered documents into ``config.output_dir``.

    Returns the list of paths written.
    """
    out_dir = (config.root / config.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if summary is not None:
        summary_path = out_dir / config.output_summary
        summary_path.write_text(summary, encoding="utf-8")
        written.append(summary_path)

    if full is not None:
        full_path = out_dir / config.output_full
        full_path.write_text(full, encoding="utf-8")
        written.append(full_path)

    if mini is not None:
        mini_path = out_dir / config.output_mini
        mini_path.write_text(mini, encoding="utf-8")
        written.append(mini_path)

    if diff is not None:
        diff_path = out_dir / config.output_diff
        diff_path.write_text(diff, encoding="utf-8")
        written.append(diff_path)

    return written
