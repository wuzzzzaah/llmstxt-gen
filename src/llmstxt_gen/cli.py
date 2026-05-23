"""Typer CLI for llmstxt-gen."""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from llmstxt_gen.cache import (
    deserialize_module,
    get_sha256,
    load_cache,
    save_cache,
    serialize_module,
)
from llmstxt_gen.config import LlmsTxtConfig, load_config
from llmstxt_gen.diff import GitError, get_changed_files
from llmstxt_gen.parsers import parser_for
from llmstxt_gen.parsers.base import ParsedModule
from llmstxt_gen.pruner import estimate_total_tokens, prune_modules
from llmstxt_gen.renderer import render_diff, render_full, render_mini, render_summary
from llmstxt_gen.walker import walk_repository
from llmstxt_gen.watcher import iter_changes
from llmstxt_gen.writer import write_outputs

app = typer.Typer(
    add_completion=False,
    help="Generate AST-derived llms.txt files from a source repository.",
)


def _collect_modules(
    config: LlmsTxtConfig,
    verbose: bool = False,
    incremental: bool = False,
    no_cache: bool = False,
) -> list[ParsedModule]:
    modules: list[ParsedModule] = []
    root = config.root.resolve()

    cache_path = Path(config.output_dir) / config.cache_path
    cache_data = {} if no_cache else load_cache(cache_path)
    new_cache_data = {}

    for source_file in walk_repository(config):
        try:
            rel_path = source_file.path.resolve().relative_to(root).as_posix()
        except ValueError:
            rel_path = str(source_file.path)

        content_hash = get_sha256(source_file.content)
        cached_entry = cache_data.get(rel_path)

        if (
            incremental
            and cached_entry
            and cached_entry.get("hash") == content_hash
            and "module" in cached_entry
        ):
            if verbose:
                typer.echo(f"cache hit: {rel_path}")
            module = deserialize_module(cached_entry["module"])
            new_cache_data[rel_path] = cached_entry
        else:
            parser = parser_for(source_file.language)
            if parser is None:
                continue
            if hasattr(parser, "include_private"):
                parser.include_private = config.include_private
            try:
                module = parser.parse(source_file)
            except Exception as exc:  # pragma: no cover - defensive
                if verbose:
                    typer.echo(f"skip {source_file.path}: {exc}", err=True)
                continue
            module.path = rel_path
            if verbose:
                typer.echo(
                    f"parsed {module.path} ({len(module.functions)} fns, {len(module.classes)} classes)"
                )
            new_cache_data[rel_path] = {
                "hash": content_hash,
                "module": serialize_module(module),
            }

        modules.append(module)

    if not no_cache:
        save_cache(cache_path, new_cache_data)

    return modules


@app.command()
def generate(
    path: Annotated[Path, typer.Argument(help="Project root to scan.")] = Path("."),
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Override output directory."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print output to stdout instead of writing files."),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Show per-file details.")] = False,
    no_full: Annotated[
        bool,
        typer.Option("--no-full", help="Skip generating llms-full.txt."),
    ] = False,
    no_mini: Annotated[
        bool,
        typer.Option("--no-mini", help="Skip generating llms-mini.txt."),
    ] = False,
    incremental: Annotated[
        bool,
        typer.Option("--incremental", help="Use cache to skip unchanged files."),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable cache entirely."),
    ] = False,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to a specific pyproject.toml."),
    ] = None,
    emit_frontmatter: Annotated[
        bool,
        typer.Option("--emit-frontmatter", help="Include YAML front-matter in llms-full.txt."),
    ] = False,
    diff: Annotated[
        str | None,
        typer.Option(
            help="Limit to files changed since git ref (e.g. 'HEAD', 'main').",
            show_default=False,
        ),
    ] = None,
    watch: Annotated[
        bool,
        typer.Option("--watch", help="Watch for file changes and regenerate automatically."),
    ] = False,
) -> None:
    """Generate ``llms.txt`` (and ``llms-full.txt``) for a project."""
    if watch and diff:
        typer.echo("Error: --watch and --diff cannot be used together.", err=True)
        raise typer.Exit(code=1)

    cfg = load_config(path, config_path=config)
    if output_dir is not None:
        cfg.output_dir = str(output_dir)
    if emit_frontmatter:
        cfg.emit_frontmatter = True

    modules = _collect_modules(
        cfg,
        verbose=verbose,
        incremental=incremental,
        no_cache=no_cache,
    )

    if diff is not None:
        try:
            changed_files = get_changed_files(diff, cfg.root)
        except GitError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from None

        modules = [m for m in modules if m.path in changed_files]
        if not modules:
            typer.echo(f"No changed files found for ref '{diff}'.", err=True)
            raise typer.Exit(code=1)

        diff_content = render_diff(modules, cfg)
        if dry_run:
            typer.echo("===== llms-diff.txt =====")
            typer.echo(diff_content)
            return
        written = write_outputs(cfg, diff=diff_content)
        for p in written:
            typer.echo(f"wrote {p}")
        return

    if not modules:
        typer.echo("No source files found to parse.", err=True)
        raise typer.Exit(code=1)

    summary_modules = prune_modules(modules, cfg, cfg.max_tokens_summary, render_summary)
    summary = render_summary(summary_modules, cfg)
    full = None if no_full else render_full(
        prune_modules(modules, cfg, cfg.max_tokens_full, render_full), cfg
    )
    mini = None if no_mini else render_mini(modules, cfg)

    if dry_run:
        typer.echo("===== llms.txt =====")
        typer.echo(summary)
        if full is not None:
            typer.echo("===== llms-full.txt =====")
            typer.echo(full)
        if mini is not None:
            typer.echo("===== llms-mini.txt =====")
            typer.echo(mini)
        return

    written = write_outputs(cfg, summary, full=full, mini=mini)
    for p in written:
        typer.echo(f"wrote {p}")

    if watch:
        typer.echo(f"Watching for changes in {cfg.root.resolve()}...")
        try:
            for changes in iter_changes(cfg.root):
                start_time = time.time()
                # Re-collect modules (cache handles skipping unchanged)
                modules = _collect_modules(
                    cfg,
                    verbose=verbose,
                    incremental=True,
                    no_cache=no_cache,
                )

                summary_modules = prune_modules(modules, cfg, cfg.max_tokens_summary, render_summary)
                summary = render_summary(summary_modules, cfg)
                full = None if no_full else render_full(
                    prune_modules(modules, cfg, cfg.max_tokens_full, render_full), cfg
                )
                mini = None if no_mini else render_mini(modules, cfg)

                write_outputs(cfg, summary, full=full, mini=mini)

                elapsed = time.time() - start_time
                timestamp = datetime.now().strftime("%H:%M:%S")
                typer.echo(f"[{timestamp}] Rebuilt in {elapsed:.1f}s ({len(changes)} files changed)")
        except KeyboardInterrupt:
            typer.echo("\nWatching stopped.")
            raise typer.Exit(code=0)


@app.command()
def validate(
    path: Annotated[
        Path,
        typer.Argument(help="Path to an existing llms.txt file or its containing directory."),
    ] = Path("llms.txt"),
) -> None:
    """Validate that an existing ``llms.txt`` file is spec-compliant.

    Checks for H1 heading, optional blockquote, sections, valid links, and
    unique anchor targets. Exits with code ``1`` if any violations are found.
    """
    target = path if path.is_file() else path / "llms.txt"
    if not target.is_file():
        typer.echo(f"not found: {target}", err=True)
        raise typer.Exit(code=1)

    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: list[str] = []

    # Filter for non-empty lines but keep track of original line numbers (1-indexed)
    non_empty_lines = [(i + 1, ln) for i, ln in enumerate(lines) if ln.strip()]

    if not non_empty_lines:
        typer.echo(f"invalid: {target} is empty", err=True)
        raise typer.Exit(code=1)

    # Rule 1: H1 heading present as the first non-empty line
    first_idx, first_line = non_empty_lines[0]
    if not first_line.startswith("# "):
        violations.append(f"L{first_idx}: missing top-level H1 heading (e.g. '# Project')")

    # Rule 2: Optional blockquote immediately after H1
    # If any other non-empty line exists before a blockquote (other than H1), or
    # if a blockquote exists later, it's a violation?
    # Spec: "Optional blockquote (> ...) immediately after H1"
    # I'll check if any blockquote exists and if it's NOT the second non-empty line.
    for i, (lno, ln) in enumerate(non_empty_lines):
        if ln.strip().startswith("> "):
            if i != 1:
                violations.append(f"L{lno}: blockquote must immediately follow H1 heading")
            break

    # Rule 3: At least one ## Section heading
    if not any(ln.startswith("## ") for _, ln in non_empty_lines):
        violations.append("invalid: no '##' section found")

    # Rule 4: All markdown links in - label lines have non-empty labels and URLs
    link_re = re.compile(r"\[(.*?)\]\((.*?)\)")
    for lno, ln in non_empty_lines:
        if ln.strip().startswith("- "):
            for label, url in link_re.findall(ln):
                if not label.strip():
                    violations.append(f"L{lno}: empty link label")
                if not url.strip():
                    violations.append(f"L{lno}: empty link URL")

    # Rule 5: No duplicate anchor targets
    anchor_re = re.compile(r'<(?:a|span)[^>]*(?:id|name)=["\'](.*?)["\']', re.IGNORECASE)
    seen_anchors: dict[str, int] = {}
    for lno, ln in non_empty_lines:
        for anchor in anchor_re.findall(ln):
            if anchor in seen_anchors:
                violations.append(
                    f"L{lno}: duplicate anchor '{anchor}' (previously seen on L{seen_anchors[anchor]})"
                )
            else:
                seen_anchors[anchor] = lno

    if violations:
        for v in violations:
            typer.echo(v, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"valid: {target}")


@app.command()
def stats(
    path: Annotated[Path, typer.Argument(help="Project root to scan.")] = Path("."),
    incremental: Annotated[
        bool,
        typer.Option("--incremental", help="Use cache to skip unchanged files."),
    ] = False,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable cache entirely."),
    ] = False,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to a specific pyproject.toml."),
    ] = None,
) -> None:
    """Print a summary of files scanned, symbols extracted, and tokens used."""
    cfg = load_config(path, config_path=config)
    modules = _collect_modules(
        cfg,
        incremental=incremental,
        no_cache=no_cache,
    )
    fn_count = sum(len(m.functions) for m in modules)
    method_count = sum(len(c.methods) for m in modules for c in m.classes)
    cls_count = sum(len(m.classes) for m in modules)
    languages = sorted({m.language for m in modules})
    total_tokens = estimate_total_tokens(modules)

    typer.echo(f"files       : {len(modules)}")
    typer.echo(f"functions   : {fn_count}")
    typer.echo(f"classes     : {cls_count}")
    typer.echo(f"methods     : {method_count}")
    typer.echo(f"languages   : {', '.join(languages) if languages else '(none)'}")
    typer.echo(f"est. tokens : {total_tokens}")


def main() -> None:  # pragma: no cover
    """Entry point used by ``python -m llmstxt_gen``."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
    sys.exit(0)
