# llmstxt-gen

> AST-aware `llms.txt` generator for Python, JavaScript/TypeScript, Go, and Rust codebases.

[![PyPI version](https://img.shields.io/pypi/v/llmstxt-gen.svg)](https://pypi.org/project/llmstxt-gen/)
[![Python versions](https://img.shields.io/pypi/pyversions/llmstxt-gen.svg)](https://pypi.org/project/llmstxt-gen/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/wuzzzzaah/llmstxt-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/wuzzzzaah/llmstxt-gen/actions/workflows/ci.yml)

## What problem this solves

LLM coding agents work best when they have an accurate, up-to-date map of the code they are working on. The [`llms.txt`](https://llmstxt.org/) standard exists to give them exactly that: a single Markdown file at the root of a project that lists the public surface area and points at deeper documentation.

Most existing generators build that file by scraping a project's published docs site. Scrapers go stale the moment your code changes, they bring along marketing prose the agent does not need, and they cannot describe code that has not been documented yet. The result is an `llms.txt` that confidently lists deprecated APIs.

`llmstxt-gen` takes a different approach. It reads your Python, JavaScript/TypeScript, Go, or Rust source code directly, parses it with tree-sitter into an Abstract Syntax Tree, and extracts the things an agent actually needs: function signatures, type hints, docstrings, class hierarchies, and exported symbols. The result is a token-efficient, always-current Markdown file you can regenerate from a pre-commit hook or a CI job.

No scraping. No cloud calls. No framework lock-in.

## Installation

```sh
pip install llmstxt-gen
```

Requires Python 3.11 or newer. The PyPI distribution name is `llmstxt-gen`; the installed CLI command and Python import name are both `llmstxt-gen`.

## Quick start

From the root of any Python, JavaScript/TypeScript, Go, or Rust project:

```sh
llmstxt-gen generate
```

You will get two files in the project root:

- `llms.txt`: a compact summary suitable for inclusion in an agent's initial context
- `llms-full.txt`: the full detailed reference

To preview without writing files:

```sh
llmstxt-gen generate --dry-run
```

To get a quick read on what would be included:

```sh
llmstxt-gen stats
```

## Example output

A small Python module like:

```python
"""Tiny calculator module."""

def add(a: int, b: int = 0) -> int:
    """Return the sum of a and b."""
    return a + b
```

produces this entry in `llms-full.txt`:

```markdown
## src/calc.py

Tiny calculator module.

### Functions

#### `add(a: int, b: int = 0) -> int`

Return the sum of a and b.
```

and a one-line entry in `llms.txt`:

```markdown
calc: Tiny calculator module.
```

## Configuration

All options live in your `pyproject.toml` under `[tool.llmstxt_gen]`. Every key is optional.

| Option | Type | Default | Description |
|---|---|---|---|
| `name` | string | directory name | Project name shown in the heading |
| `description` | string | `""` | Short tagline shown as a blockquote |
| `version` | string | `""` | Project version |
| `include` | list of strings | `[]` (all) | Paths to scan, relative to the repo root |
| `exclude` | list of strings | `[]` | Additional patterns to skip, beyond `.gitignore` |
| `extensions` | list of strings | `[".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs"]` | File extensions to consider |
| `output_dir` | string | `"."` | Where to write the output files |
| `output_summary` | string | `"llms.txt"` | Filename for the summary file |
| `output_full` | string | `"llms-full.txt"` | Filename for the full reference |
| `include_private` | bool | `false` | Include private or non-exported symbols |
| `max_tokens_summary` | int | `8000` | Token budget for `llms.txt` |
| `max_tokens_full` | int | `32000` | Token budget for `llms-full.txt` |
| `languages` | list of strings | `["python", "typescript", "go", "rust"]` | Parsers to activate |

Example:

```toml
[tool.llmstxt_gen]
include = ["src/"]
exclude = ["src/internal/"]
include_private = false
max_tokens_summary = 6000
```

## CI integration

### Pre-commit hook

```yaml
repos:
  - repo: local
    hooks:
      - id: llmstxt-gen
        name: llmstxt-gen
        entry: llmstxt-gen generate
        language: system
        pass_filenames: false
        always_run: true
```

### GitHub Actions

```yaml
name: Update llms.txt
on:
  push:
    branches: [main]

jobs:
  update:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install llmstxt-gen
      - run: llmstxt-gen generate
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: refresh llms.txt"
```

More integrations live in [docs/ci-integration.md](docs/ci-integration.md).

## How it compares to scraper-based approaches

Scrapers like [llmstxt.org generators](https://llmstxt.org/) crawl a published documentation site and concatenate the rendered HTML. They work without source access, which is their main advantage. The drawbacks are real:

- They cannot describe undocumented code, so newer modules are invisible.
- They drift the moment your code lands faster than your docs site rebuilds.
- They include navigation chrome, marketing copy, and rendered examples that bloat the agent's context window.
- They cannot reliably recover type information, since rendered HTML is lossy.

`llmstxt-gen` reads the source. It will always reflect what is actually in the repository, and it produces output that maps one-to-one with the symbols an agent will end up calling.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and pull requests are welcome.

## License

MIT. See [LICENSE](LICENSE).

## Roadmap

Today: Python, JavaScript/TypeScript, Go, Rust.

Next: Ruby, Java, C# — in that order. The full plan with rationale, scope, and contribution instructions lives in [docs/roadmap.md](docs/roadmap.md).

Beyond language support, planned work:

- Optional semantic pruning via a local model
- A hosted GitHub App for zero-config setup
- A Rust reimplementation of the core for very large monorepos
