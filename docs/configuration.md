# Configuration

llmstxt-gen is designed to work with zero configuration, but you can customize its behavior via `pyproject.toml`.

## Configuration file

Add a `[tool.llmstxt_gen]` section to your `pyproject.toml` at the root of your project:

```toml
[tool.llmstxt_gen]
name = "my-project"
description = "A short description of my project"
include = ["src/"]
exclude = ["src/internal/"]
include_private = false
```

## Options

### `name`
- **Type**: `string`
- **Default**: The name of the project directory.
- **Description**: The project name used in the `llms.txt` header.

### `description`
- **Type**: `string`
- **Default**: `""`
- **Description**: A short description of the project, displayed as a blockquote.

### `version`
- **Type**: `string`
- **Default**: `""`
- **Description**: The project version.

### `include`
- **Type**: `list of strings`
- **Default**: `[]` (includes all files with supported extensions)
- **Description**: A list of glob patterns for files or directories to include.

### `exclude`
- **Type**: `list of strings`
- **Default**: `[]`
- **Description**: A list of glob patterns for files or directories to exclude. Always excludes `.git`, `node_modules`, etc.

### `extensions`
- **Type**: `list of strings`
- **Default**: `[".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".kt", ".kts"]`
- **Description**: File extensions to scan.

### `output_dir`
- **Type**: `string`
- **Default**: `"."`
- **Description**: The directory where output files will be written.

### `output_summary`
- **Type**: `string`
- **Default**: `"llms.txt"`
- **Description**: The filename for the compact summary.

### `output_full`
- **Type**: `string`
- **Default**: `"llms-full.txt"`
- **Description**: The filename for the detailed reference.

### `include_private`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: Whether to include symbols considered private (e.g., prefixed with `_` in Python, or not exported in TypeScript/Go).

### `max_tokens_summary`
- **Type**: `integer`
- **Default**: `8000`
- **Description**: Token limit for the summary file.

### `max_tokens_full`
- **Type**: `integer`
- **Default**: `32000`
- **Description**: Token limit for the full reference file.

### `languages`
- **Type**: `list of strings`
- **Default**: `["python", "typescript", "go", "kotlin"]`
- **Description**: The language parsers to activate.

## Supported languages

- **Python**: Parses `.py` files.
- **JavaScript/TypeScript**: Parses `.js`, `.jsx`, `.ts`, `.tsx` files.
- **Go**: Parses `.go` files.
- **Kotlin**: Parses `.kt`, `.kts` files.
