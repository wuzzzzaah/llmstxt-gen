# Contributing to codexa

Thanks for your interest in improving codexa. This document explains how to get set up locally, how to run the test suite and quality checks, and how to add support for a new language.

## Development setup

Clone the repository and create a fresh virtual environment:

```sh
git clone https://github.com/wuzzzzaah/codexa.git
cd codexa
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify the install:

```sh
codexa --help
```

## Running the test suite

```sh
pytest
```

For a coverage report:

```sh
pytest --cov=codexa --cov-report=term-missing
```

The project enforces a minimum of 80 percent line coverage in CI.

## Linting and type checking

```sh
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

All three must pass before a pull request can be merged.

## Branch and PR conventions

- Branch from `main`. Use short, descriptive branch names such as `fix-walker-gitignore` or `add-ruby-parser`.
- Keep pull requests focused on one change. Split unrelated work into separate PRs.
- Write the PR description in terms of the user-facing effect, not the implementation detail.
- Add or update tests for every behavior change. New parser support requires a fixture project under `tests/fixtures/`.
- Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change.

## How to add support for a new language

1. Add the tree-sitter binding to `dependencies` in `pyproject.toml`.
2. Create `src/codexa/parsers/<language>.py` implementing `BaseParser`. The parser must convert a `SourceFile` into a `ParsedModule` and respect the `include_private` flag.
3. Register the parser in `src/codexa/parsers/__init__.py` inside `parser_for(language)`.
4. Extend `EXTENSION_TO_LANGUAGE` in `src/codexa/walker.py` with any new file extensions.
5. Add the extensions to `DEFAULT_EXTENSIONS` and the language name to `DEFAULT_LANGUAGES` in `src/codexa/config.py`.
6. Add a small fixture project under `tests/fixtures/sample_<language>/` exercising at least one function, one class with a method, and one private symbol.
7. Add `tests/test_<language>_parser.py` with explicit assertions for each of the symbol types your parser supports.
8. Document the new language in `README.md` and in `docs/configuration.md`.

## Code of conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be respectful in every interaction.
