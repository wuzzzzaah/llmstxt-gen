# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Swift parser backed by tree-sitter-swift. Extracts doc comments, public functions, classes, structs, enums, protocols, actors, and extensions. Handles async/throws and generic constraints.
- PHP parser backed by tree-sitter-php. Extracts PHPDoc comments, public classes, interfaces, traits, enums, methods, properties, and constants. Respects `include_private` flag.
- Java parser backed by tree-sitter-java. Extracts package Javadoc, public/protected classes, interfaces, enums, records, and their members (methods, constructors, fields, enum constants). Supports generics, annotations, and flattened inner classes.
- Ruby parser backed by tree-sitter-ruby. Extracts modules, classes, methods, constants, and expands `attr_*` macros. Respects private/protected visibility.
- C# parser backed by tree-sitter-c-sharp. Extracts XML doc comments, public/protected classes, structs, interfaces, records, enums, and their members. Preserves attributes as decorators and generic constraints in signatures.
- Rust parser backed by tree-sitter-rust. Extracts module doc comments (`//!`, `///`), public functions (including generics and where clauses), structs, enums, traits, impl blocks, type aliases, and constants/statics.
- Scala parser backed by tree-sitter-scala. Extracts ScalaDoc, classes, objects, traits, enums, methods, and members. Handles Scala 3 features like given instances and extension methods. Companion objects are merged into their associated classes.

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
