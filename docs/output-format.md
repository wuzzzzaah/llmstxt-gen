# Output format

codexa produces two Markdown files. This document walks through what each section looks like, using a small worked example.

## The input

Imagine a tiny library at `src/greet/core.py`:

```python
"""Greet people in different languages."""

LANGUAGES = ["en", "es"]


def hello(name: str, lang: str = "en") -> str:
    """Return a greeting for ``name`` in the given language."""
    return f"hello {name}" if lang == "en" else f"hola {name}"


class Greeter:
    """Stateful greeter that remembers a default language."""

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang

    def greet(self, name: str) -> str:
        """Greet ``name`` in the configured language."""
        return hello(name, self.lang)
```

## llms.txt (summary)

`llms.txt` is meant to live inside an agent's initial prompt. It is intentionally short.

```markdown
# greet

> A library for greeting people in different languages.

core: Greet people in different languages.

## Modules

- [core](llms-full.txt#src-greet-core-py): Greet people in different languages.
```

Each module produces one line in the "modules" section. The link's anchor matches an `id` written into `llms-full.txt`, so an agent can resolve the reference deterministically.

## llms-full.txt (detailed reference)

`llms-full.txt` is the long-form reference. It is structured so an agent can scan it linearly and pick up complete function signatures and docstrings without needing to look at the source.

```markdown
# greet

> A library for greeting people in different languages.

## src/greet/core.py
<a id="src-greet-core-py"></a>

Greet people in different languages.

### Functions

#### `hello(name: str, lang: str = "en") -> str`

Return a greeting for ``name`` in the given language.

### Classes

#### `Greeter`

Stateful greeter that remembers a default language.

##### Methods

###### `__init__(self, lang: str = "en") -> None`

###### `greet(self, name: str) -> str`

Greet ``name`` in the configured language.

### Constants

- `LANGUAGES`
```

## Why this shape

Three things drive the format:

1. **Heading depth carries semantic weight.** A top-level heading is the project, `##` is a module, `###` is a category (functions, classes, constants), and `####` and below are individual symbols. Agents that chunk Markdown by heading depth get clean, semantically meaningful units.
2. **Signatures are rendered as code.** Backtick fencing means an agent's tokenizer treats the signature as a single unit, and human readers can read it without parsing prose.
3. **Anchors are deterministic.** They are derived from the file path, lowercase, with non-alphanumeric runs collapsed to hyphens. This means a stable link from the summary to the detail document.

## Token budgets

When parsed output exceeds the configured token budget, the pruner removes content in a fixed order: constants first, then parameter type detail, then method docstrings, then methods entirely, then function docstrings. Module names, class names, and class docstrings are always preserved.
