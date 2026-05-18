# Language support roadmap

This document tracks which languages `llmstxt-gen` supports today, which are coming next, and which are explicitly out of scope. The list is updated as parsers land.

If you want to contribute a parser, the step-by-step guide is in [CONTRIBUTING.md](../CONTRIBUTING.md). Each language on this roadmap can be picked up as a GitHub issue — see "How to claim a language" at the bottom.

## Shipped

| Language | Version | Notes |
|---|---|---|
| Python | v0.1.0 | Tree-sitter-python. Functions, classes, decorators, async, properties, type hints, module docstrings. |
| JavaScript / TypeScript | v0.1.0 | Tree-sitter-javascript and tree-sitter-typescript. Exports, JSDoc, interfaces, type aliases, arrow functions. |
| Go | v0.2.0 | Tree-sitter-go. Package doc comments, exported functions, methods attached to receivers, structs, interfaces (with methods), type aliases, constants. |
| Ruby | v0.2.0 | Tree-sitter-ruby. Modules, classes, methods, constants, attr_* expansion, visibility filtering. |

## Next wave — priority order

### 1. Rust

**Why:** Rust has the highest growth in agent-driven coding workflows. Cargo monorepos are large, the type system is rich, and accurate context matters more than in dynamically-typed languages. tree-sitter-rust is one of the most battle-tested grammars in the ecosystem.

**Scope for v1:**
- Module doc comments (`//!` for inner, `///` for outer)
- Public functions: name, generics, parameters, return types, doc comments
- Public structs and enums with their fields and variants
- Public traits and their method signatures
- Public type aliases
- `impl` blocks: attach methods to their target type
- Public constants and statics with their types

**Filter rule:** non-`pub` items are skipped unless `include_private = true`. `pub(crate)`, `pub(super)`, and `pub(in ...)` count as exported.

**Mapping notes:**
- Trait impls map to `ParsedClass.methods` on the target type
- Enum variants map to `ParsedClass.class_vars` (treat the enum as the class)
- Lifetimes and generic constraints should appear verbatim in the rendered signature

**Status:** open for contribution

---

### 2. Ruby

**Why:** Rails codebases remain enormous and agent-driven refactors are common. Ruby's dynamic nature means signature info is thinner than in typed languages, but module + method + docstring extraction still produces useful llms.txt entries.

**Scope for v1:**
- Module-level RDoc/YARD-style comments (`# comment block` immediately above a definition)
- Top-level methods with their parameter lists and doc comments
- Classes with their methods, ancestors (superclass + included modules)
- Modules with their methods and nested constants
- Class-level constants
- `attr_accessor`, `attr_reader`, `attr_writer` declarations (expand to method names)

**Filter rule:** methods marked `private` or `protected` (via `private` / `protected` keywords) are skipped unless `include_private = true`. Methods prefixed with `_` are not considered private in Ruby convention — do not filter them.

**Mapping notes:**
- Modules and classes both map to `ParsedClass`. Use `bases` for `<` (inheritance) and `include` / `extend` / `prepend`.
- YARD `@param` and `@return` tags should be preserved in the docstring as plain text — do not try to coerce them into typed signatures.

**Status:** open for contribution

---

### 3. Java

**Why:** Enterprise codebases are vast and JVM workflows are widely targeted by coding agents. Java's static typing makes it a high-value parser; the generated llms.txt entries are dense with useful information per byte.

**Scope for v1:**
- Package-level Javadoc (the comment block above the `package` statement)
- Public classes, interfaces, enums, records, and annotations
- Public fields, methods, and constructors with full type signatures including generics
- Javadoc comments on classes and methods (preserve `@param`, `@return`, `@throws` verbatim)
- Inner classes — recurse, attach to parent's `ParsedClass.methods` or a sibling `ParsedClass` (decide in implementation; document the choice)

**Filter rule:** `private` and package-private members are skipped unless `include_private = true`. `protected` counts as exported by default (it is part of the public API for subclasses).

**Mapping notes:**
- Java records map cleanly to `ParsedClass` with components as `class_vars`
- Annotations on a method should appear in `ParsedFunction.decorators` (use the `@` prefix in rendered output)
- Generic bounds (`T extends Comparable<T>`) appear verbatim in the signature

**Status:** open for contribution

---

### 4. C#

**Why:** .NET workflows are growing in agent-assisted development. C# is structurally similar to Java but with first-class properties, records, and pattern matching. Same density-of-useful-info argument as Java.

**Scope for v1:**
- File-level and namespace-level XML doc comments (`/// <summary>` blocks)
- Public classes, structs, interfaces, records, enums
- Public methods, properties, fields, and events with full type signatures
- XML doc comments preserved as docstrings (strip the `///` prefix but keep the structure)
- Attributes (preserve as decorators)
- Generic constraints (`where T : IComparable<T>`)

**Filter rule:** `private`, `internal`, and `protected internal` members are skipped unless `include_private = true`. `public` and `protected` are kept.

**Mapping notes:**
- C# properties map to a pair of `ParsedFunction` (getter + setter) or a single one flagged `is_property` — implementer's choice; document the decision
- `record` types map to `ParsedClass` with positional parameters as `class_vars`
- `partial` classes: merge into a single `ParsedClass` if they live in the same file; do not attempt cross-file merging in v1

**Status:** open for contribution

## Under consideration (no commitment yet)

Languages with mature tree-sitter grammars but smaller agent-coding demand or significant edge cases:

| Language | Why we'd want it | Why we're holding |
|---|---|---|
| Kotlin | Android + modern JVM | Most Kotlin codebases are mixed with Java; pairs better with a Java parser landing first |
| Swift | Apple ecosystem | tree-sitter-swift exists but maturity varies; investigate before committing |
| PHP | WordPress, Laravel, huge installed base | Strong demand, low priority because most PHP work is not yet agent-driven |
| C / C++ | Systems and kernel work | Preprocessor and templates create thorny rendering decisions; needs a dedicated design pass |
| Elixir | Phoenix, distributed systems | Smaller userbase but extremely high agent-friendliness due to functional purity |
| Scala | JVM functional + Spark | Macros and implicit resolution are hard; revisit when tree-sitter-scala matures |

## Explicitly out of scope (for now)

- **Markdown, YAML, TOML, JSON.** These are configuration, not API surface. An llms.txt should describe behavior, not config syntax. We may revisit if a clear use case emerges.
- **HTML, CSS, SCSS.** Same reasoning as above.
- **Assembly languages.** No tree-sitter grammar coverage and unclear value for agent context.
- **Notebooks (.ipynb, .qmd).** Parsing the embedded code makes sense, but the cell-level extraction model does not fit our `ParsedModule` shape. Worth a dedicated discussion if demand is real.

## How to claim a language

1. Comment "I want to take this" on the language's GitHub issue (or open one if it does not exist yet).
2. Read [CONTRIBUTING.md](../CONTRIBUTING.md) — specifically the "How to add support for a new language" section. It walks through every file you will touch.
3. Read the existing Python and Go parsers as references. Python is the cleanest example for typed languages; Go is the cleanest example for languages without docstrings-as-string-literals.
4. Open a draft PR early so we can review the parsed-data shape before you go deep on edge cases.

## Design principles for new parsers

These are the rules every parser should follow. They are why the pipeline stays language-agnostic.

1. **Source is the only ground truth.** Never reach out to external metadata sources (no `npm view`, no `cargo metadata`, no LSP).
2. **No execution.** Tree-sitter parses; no language runtime is invoked.
3. **Public surface only by default.** Exporting rules differ by language but the principle is the same: what a user of the library will call, not what its authors wrote.
4. **No new dataclasses.** Map your language's constructs onto the existing `ParsedModule`, `ParsedClass`, `ParsedFunction`, `ParsedParameter`, `ParsedConstant`. If you genuinely cannot, open a design issue before writing code.
5. **Empty docstrings are normal, not errors.** Many languages do not require documentation; render the function signature alone and move on.
6. **Test against a real fixture, not just unit tests.** Every parser ships with a `tests/fixtures/sample_<lang>/` directory containing at least one of each construct the parser claims to handle.
