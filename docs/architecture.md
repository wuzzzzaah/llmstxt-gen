# Architecture

llmstxt-gen is a small, linear pipeline. Each stage has a narrow job and produces a value the next stage consumes.

```
+------------+    +----------+    +---------+    +----------+    +--------+
|  walker.py | -> | parser   | -> | pruner  | -> | renderer | -> | writer |
+------------+    +----------+    +---------+    +----------+    +--------+
   SourceFile      ParsedModule    ParsedModule     Markdown      llms.txt
```

## Stage 1: walker

`walker.py` accepts a resolved `LlmsTxtConfig`, walks the repository, and yields a `SourceFile` for every file that survives filtering. Filtering removes:

- files outside the user's `include` patterns
- files matched by `.gitignore`
- files matched by the user's `exclude` patterns
- files in always-ignored directories like `.git`, `node_modules`, and `__pycache__`
- files whose extension is not in the configured set
- binary files

The walker is intentionally dumb: it knows nothing about languages beyond extension-to-language mapping.

## Stage 2: parsers

Each parser is a subclass of `BaseParser` and lives in `src/llmstxt_gen/parsers/`. A parser's job is to turn a `SourceFile` into a `ParsedModule`. The Python parser uses `tree-sitter-python`; the TypeScript parser uses `tree-sitter-typescript` (or the JavaScript grammar for `.js` and `.jsx` files).

A `ParsedModule` is the universal currency of the pipeline. Once a file has been parsed, no downstream stage cares what language it came from.

### Why tree-sitter, not Python's `ast`?

Three reasons:

1. **Polyglot.** A single library handles every language we ever want to support. The same node-walking patterns work for Python, TypeScript, and any future addition.
2. **Incremental and error-tolerant.** tree-sitter happily parses files that contain syntax errors. Python's `ast` module raises on the first error, which means a single broken file can take down the entire run.
3. **No code execution.** Tree-sitter never imports or evaluates the code it parses. Python's `ast.parse` does not execute code either, but extending support to JavaScript via a Python-native parser (e.g., calling out to Node) would.

## Stage 3: pruner

`pruner.py` takes the full list of `ParsedModule` objects and reduces them to fit a token budget. It works by deep-copying the input and then deleting fields in a fixed priority order, lowest-value first. The exact order is documented in [output-format.md](output-format.md).

Token counting uses `tiktoken` with the `cl100k_base` encoding when available, and falls back to a four-characters-per-token heuristic when `tiktoken` is not installed.

## Stage 4: renderer

`renderer.py` walks the (possibly pruned) modules and produces two strings: the `llms.txt` summary and the `llms-full.txt` detail. The renderer is a pure function: same input always produces the same output bytes. That property is what makes the "run in CI and commit the result" pattern safe.

## Stage 5: writer

`writer.py` is a thin wrapper around `Path.write_text`. It exists so the renderer and the CLI never have to think about filesystem semantics.

## Configuration

`config.py` is loaded once, very early, and passed by value to every stage. There is no global state. Tests instantiate `LlmsTxtConfig` directly without touching disk.
