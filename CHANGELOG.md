# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Java parser backed by tree-sitter-java. Extracts package Javadoc, public/protected classes, interfaces, enums, records, and their members (methods, constructors, fields, enum constants). Supports generics, annotations, and flattened inner classes.
- Ruby parser backed by tree-sitter-ruby. Extracts modules, classes, methods, constants, and expands `attr_*` macros. Respects private/protected visibility.
- C# parser backed by tree-sitter-c-sharp. Extracts XML doc comments, public/protected classes, structs, interfaces, records, enums, and their members. Preserves attributes as decorators and generic constraints in signatures.
- Rust parser backed by tree-sitter-rust. Extracts module doc comments (`//!`, `///`), public functions (including generics and where clauses), structs, enums, traits, impl blocks, type aliases, and constants/statics.
- Elixir parser backed by tree-sitter-elixir. Extracts `@moduledoc`, public functions (`def`), macros (`defmacro`), structs (`defstruct`), behaviours, and protocols/implementations. Handles multiple function heads and `@spec` type hints.

## [0.2.0] - 2026-05-18

### Added
- Go parser backed by tree-sitter-go. Extracts package doc comments, exported functions, methods attached to their receiver types, structs, interfaces (including interface methods), type aliases, and exported constants/variables.

### Changed
- README and configuration docs now reflect Go support.

## [0.1.0] - 2026-05-18

### Added
- Initial release of llmstxt-gen.
- Python parser backed by tree-sitter.
- JavaScript and TypeScript parser backed by tree-sitter.
- File-system walker that honors `.gitignore` and user-configured exclude patterns.
- Token-aware pruner with five staged pruning levels.
- Renderer producing spec-compliant `llms.txt` and `llms-full.txt` Markdown.
- Typer-based CLI with `generate`, `validate`, and `stats` commands.
- Configuration loader for `[tool.llmstxt_gen]` blocks in `pyproject.toml`.
