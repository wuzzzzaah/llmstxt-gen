# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of codexa.
- Python parser backed by tree-sitter.
- JavaScript and TypeScript parser backed by tree-sitter.
- File-system walker that honors `.gitignore` and user-configured exclude patterns.
- Token-aware pruner with five staged pruning levels.
- Renderer producing spec-compliant `llms.txt` and `llms-full.txt` Markdown.
- Typer-based CLI with `generate`, `validate`, and `stats` commands.
- Configuration loader for `[tool.codexa]` blocks in `pyproject.toml`.
