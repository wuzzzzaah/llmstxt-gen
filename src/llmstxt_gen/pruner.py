"""Token-aware pruning.

Given a sequence of :class:`ParsedModule` objects, drop the lowest-priority
content first until the rendered output is expected to fit in a token budget.
"""

from __future__ import annotations

import copy

from llmstxt_gen.parsers.base import ParsedModule

_ENCODING: object | None
try:  # pragma: no cover - optional dependency
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _ENCODING = None


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens a string will consume.

    Uses ``tiktoken`` with the ``cl100k_base`` encoding when available, and
    falls back to a four-characters-per-token heuristic otherwise.
    """
    if _ENCODING is not None:
        return max(1, len(_ENCODING.encode(text)))  # type: ignore[attr-defined]
    return max(1, len(text) // 4)


def _module_text_estimate(module: ParsedModule) -> int:
    parts: list[str] = [module.name, module.docstring]
    for fn in module.functions:
        parts.append(fn.name)
        parts.append(fn.docstring)
        parts.append(fn.return_type)
        for p in fn.parameters:
            parts.extend([p.name, p.type_hint, p.default])
    for cls in module.classes:
        parts.append(cls.name)
        parts.append(cls.docstring)
        parts.extend(cls.bases)
        for m in cls.methods:
            parts.append(m.name)
            parts.append(m.docstring)
            parts.append(m.return_type)
            for p in m.parameters:
                parts.extend([p.name, p.type_hint, p.default])
    for c in module.constants:
        parts.extend([c.name, c.type_hint, c.value])
    return estimate_tokens("\n".join(parts))


def estimate_total_tokens(modules: list[ParsedModule]) -> int:
    """Sum the per-module token estimate across ``modules``."""
    return sum(_module_text_estimate(m) for m in modules)


def prune_modules(modules: list[ParsedModule], max_tokens: int) -> list[ParsedModule]:
    """Return a deep-copied list of modules pruned to fit in ``max_tokens``.

    Pruning proceeds in five stages, lowest-value content first:

    1. Drop constants and type aliases.
    2. Drop parameter ``type_hint`` and ``default`` details.
    3. Drop method docstrings.
    4. Drop method signatures entirely.
    5. Drop top-level function docstrings.

    Modules, class names, and class docstrings are always preserved.
    """
    pruned = [copy.deepcopy(m) for m in modules]

    if estimate_total_tokens(pruned) <= max_tokens:
        return pruned

    for module in pruned:
        module.constants = []
    if estimate_total_tokens(pruned) <= max_tokens:
        return pruned

    for module in pruned:
        for fn in module.functions:
            for p in fn.parameters:
                p.type_hint = ""
                p.default = ""
        for cls in module.classes:
            for method in cls.methods:
                for p in method.parameters:
                    p.type_hint = ""
                    p.default = ""
    if estimate_total_tokens(pruned) <= max_tokens:
        return pruned

    for module in pruned:
        for cls in module.classes:
            for method in cls.methods:
                method.docstring = ""
    if estimate_total_tokens(pruned) <= max_tokens:
        return pruned

    for module in pruned:
        for cls in module.classes:
            cls.methods = []
    if estimate_total_tokens(pruned) <= max_tokens:
        return pruned

    for module in pruned:
        for fn in module.functions:
            fn.docstring = ""

    return pruned
