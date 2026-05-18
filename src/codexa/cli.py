"""Typer CLI for codexa."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from codexa.config import CodexaConfig, load_config
from codexa.parsers import parser_for
from codexa.parsers.base import ParsedModule
from codexa.pruner import estimate_total_tokens, prune_modules
from codexa.renderer import render_full, render_summary
from codexa.walker import walk_repository
from codexa.writer import write_outputs

app = typer.Typer(
    add_completion=False,
    help="Generate AST-derived llms.txt files from a source repository.",
)


def _collect_modules(config: CodexaConfig, verbose: bool = False) -> list[ParsedModule]:
    modules: list[ParsedModule] = []
    root = config.root.resolve()
    for source_file in walk_repository(config):
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
        try:
            module.path = source_file.path.resolve().relative_to(root).as_posix()
        except ValueError:
            module.path = str(source_file.path)
        if verbose:
            typer.echo(
                f"parsed {module.path} "
                f"({len(module.functions)} fns, {len(module.classes)} classes)"
            )
        modules.append(module)
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
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to a specific pyproject.toml."),
    ] = None,
) -> None:
    """Generate ``llms.txt`` (and ``llms-full.txt``) for a project."""
    cfg = load_config(path, config_path=config)
    if output_dir is not None:
        cfg.output_dir = str(output_dir)

    modules = _collect_modules(cfg, verbose=verbose)
    if not modules:
        typer.echo("No source files found to parse.", err=True)
        raise typer.Exit(code=1)

    summary_modules = prune_modules(modules, cfg.max_tokens_summary)
    summary = render_summary(summary_modules, cfg)
    full = None if no_full else render_full(prune_modules(modules, cfg.max_tokens_full), cfg)

    if dry_run:
        typer.echo("===== llms.txt =====")
        typer.echo(summary)
        if full is not None:
            typer.echo("===== llms-full.txt =====")
            typer.echo(full)
        return

    written = write_outputs(cfg, summary, full)
    for p in written:
        typer.echo(f"wrote {p}")


@app.command()
def validate(
    path: Annotated[
        Path,
        typer.Argument(help="Path to an existing llms.txt file or its containing directory."),
    ] = Path("llms.txt"),
) -> None:
    """Validate that an existing ``llms.txt`` file is spec-compliant.

    The check verifies that the file begins with a level-one heading and
    contains at least one section listing modules. It exits with code ``1``
    when the file is missing or invalid.
    """
    target = path if path.is_file() else path / "llms.txt"
    if not target.is_file():
        typer.echo(f"not found: {target}", err=True)
        raise typer.Exit(code=1)

    text = target.read_text(encoding="utf-8")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("# "):
        typer.echo("invalid: missing top-level '# Project' heading", err=True)
        raise typer.Exit(code=1)
    if not any(ln.startswith("## ") for ln in lines):
        typer.echo("invalid: no '##' section found", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"valid: {target}")


@app.command()
def stats(
    path: Annotated[Path, typer.Argument(help="Project root to scan.")] = Path("."),
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to a specific pyproject.toml."),
    ] = None,
) -> None:
    """Print a summary of files scanned, symbols extracted, and tokens used."""
    cfg = load_config(path, config_path=config)
    modules = _collect_modules(cfg)
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
    """Entry point used by ``python -m codexa``."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
    sys.exit(0)
