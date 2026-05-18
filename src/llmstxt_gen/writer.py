"""Write rendered output to disk."""

from __future__ import annotations

from pathlib import Path

from llmstxt_gen.config import LlmsTxtConfig


def write_outputs(
    config: LlmsTxtConfig,
    summary: str,
    full: str | None,
) -> list[Path]:
    """Write the summary (and optional full) document into ``config.output_dir``.

    Returns the list of paths written.
    """
    out_dir = (config.root / config.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    summary_path = out_dir / config.output_summary
    summary_path.write_text(summary, encoding="utf-8")
    written.append(summary_path)

    if full is not None:
        full_path = out_dir / config.output_full
        full_path.write_text(full, encoding="utf-8")
        written.append(full_path)

    return written
