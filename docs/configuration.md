# Configuration

llmstxt-gen reads all of its options from your `pyproject.toml` under the `[tool.llmstxt_gen]` table. Every option has a default, so you can run `llmstxt-gen generate` against any project without writing config first.

## Project metadata

| Key | Type | Default | Description |
|---|---|---|---|
| `name` | string | directory name | Project name shown in the top-level heading. Falls back to the `[project].name` field when set. |
| `description` | string | `""` | One-line description rendered as a Markdown blockquote. Falls back to `[project].description`. |
| `version` | string | `""` | Project version. Reserved for use in future templates. |

## File selection

| Key | Type | Default | Description |
|---|---|---|---|
| `include` | list of strings | empty (entire repo) | Directories or glob patterns to scan. When set, only files matching one of these patterns are considered. |
| `exclude` | list of strings | empty | Additional patterns to skip, evaluated after the `.gitignore` rules already in effect. |
| `extensions` | list of strings | `[".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".java", ".cs", ".swift"]` | File extensions to consider. Files with any other extension are ignored. |

Patterns use the same syntax as `.gitignore` (gitwildmatch).

## Output files

| Key | Type | Default | Description |
|---|---|---|---|
| `output_dir` | string | `"."` | Directory to write output files into, relative to the project root. |
| `output_summary` | string | `"llms.txt"` | Filename for the compact summary file. |
| `output_full` | string | `"llms-full.txt"` | Filename for the detailed reference. |

## Parsing behavior

| Key | Type | Default | Description |
|---|---|---|---|
| `include_private` | bool | `false` | Include symbols whose names begin with an underscore (Python) or are not exported (JS/TS/Go). |
| `max_tokens_summary` | int | `8000` | Soft token budget for the summary file. The pruner reduces output to fit. |
| `max_tokens_full` | int | `32000` | Soft token budget for the full file. |
| `languages` | list of strings | `["python", "typescript", "go", "rust", "ruby", "java", "csharp", "swift"]` | Parsers to activate. Supported values: `python`, `typescript`, `go`, `rust`, `ruby`, `java`, `csharp`, `swift`. |

## A worked example

```toml
[tool.llmstxt_gen]
name = "my-library"
description = "A small library for doing the thing."
include = ["src/my_library/"]
exclude = ["src/my_library/_vendored/"]
include_private = false
max_tokens_summary = 6000
max_tokens_full = 24000
languages = ["python"]
```

This config scans only `src/my_library/`, skips the vendored directory, omits private symbols, and gives the renderer tighter token budgets than the defaults.
