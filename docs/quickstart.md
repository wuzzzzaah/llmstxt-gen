# Quickstart

This guide takes you from zero to a generated `llms.txt` in under a minute.

## Install

```sh
pip install llmstxt-gen
```

The PyPI distribution is `llmstxt-gen`; the CLI it installs is `codexa`.

You need Python 3.11 or newer. No other system dependencies are required: tree-sitter ships precompiled wheels for every supported platform.

## Generate your first llms.txt

From the root of any Python or TypeScript project:

```sh
codexa generate
```

You will see two new files in the project root:

- `llms.txt`: a concise summary aimed at fitting inside an agent's initial context window.
- `llms-full.txt`: the detailed reference, anchored so the summary file can link into it.

If you only want to see what would be produced without writing anything:

```sh
codexa generate --dry-run
```

## Configure what gets included

If your project layout puts source code under `src/` and you do not want test files included, add this to your `pyproject.toml`:

```toml
[tool.codexa]
include = ["src/"]
exclude = ["tests/"]
```

The full set of options is documented in [configuration.md](configuration.md).

## Get a quick sense of project size

```sh
codexa stats
```

This prints how many files were scanned, how many symbols were extracted, and the estimated token cost of the resulting document. It is useful for tuning `max_tokens_summary`.

## Validate an existing llms.txt

```sh
codexa validate llms.txt
```

Exits with code zero on success and one when the file is missing or malformed.

## Next steps

Wire `codexa generate` into your CI so the file never drifts. See [ci-integration.md](ci-integration.md).
