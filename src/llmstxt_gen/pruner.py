"""Token-aware pruning.

Given a sequence of :class:`ParsedModule` objects, drop the lowest-priority
content first until the rendered output is expected to fit in a token budget.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.parsers.base import ParsedModule

logger = logging.getLogger(__name__)


def _first_sentence(text: str) -> str:
    """Return the first sentence of a string, or the first line if no period exists."""
    if not text:
        return ""
    text = text.strip().splitlines()[0]
    if "." in text:
        text = text.split(".", 1)[0] + "."
    return text


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


def _count_references(modules: list[ParsedModule]) -> dict[str, int]:
    """Estimate module importance by counting mentions of its name in other modules.

    A module's "name" for this purpose is its path stem. We look for this
    string in the docstrings and symbol names of every other module.
    """
    counts = {m.path: 0 for m in modules}
    # Map from stem to full path(s) to handle possible name collisions
    stems: dict[str, list[str]] = {}
    for m in modules:
        stem = Path(m.path).stem
        stems.setdefault(stem, []).append(m.path)

    for m in modules:
        # Collect all text in this module that might reference others
        text_bits = [m.docstring]
        for fn in m.functions:
            text_bits.append(fn.name)
            text_bits.append(fn.docstring)
        for cls in m.classes:
            text_bits.append(cls.name)
            text_bits.append(cls.docstring)
            for method in cls.methods:
                text_bits.append(method.name)
                text_bits.append(method.docstring)
        for const in m.constants:
            text_bits.append(const.name)

        combined = " ".join(text_bits).lower()
        for stem, paths in stems.items():
            if stem.lower() in combined:
                for path in paths:
                    if path != m.path:
                        counts[path] += 1
    return counts


def prune_modules(
    modules: list[ParsedModule],
    config: LlmsTxtConfig,
    max_tokens: int,
    render_fn: Callable[[list[ParsedModule], LlmsTxtConfig], str],
) -> list[ParsedModule]:
    """Return a deep-copied list of modules pruned to fit in ``max_tokens``.

    Pruning proceeds in four stages, lowest-value content first:

    1. Truncate docstrings to first sentence.
    2. Drop constants.
    3. Drop private methods and functions.
    4. Drop entire modules (least-referenced first).

    A warning is logged when pruning occurs.
    """
    pruned = [copy.deepcopy(m) for m in modules]

    def _current_tokens() -> int:
        return estimate_tokens(render_fn(pruned, config))

    if _current_tokens() <= max_tokens:
        return pruned

    # Stage 1: Truncate docstrings
    truncated_count = 0
    for m in pruned:
        if m.docstring and m.docstring != _first_sentence(m.docstring):
            m.docstring = _first_sentence(m.docstring)
            truncated_count += 1
        for fn in m.functions:
            if fn.docstring and fn.docstring != _first_sentence(fn.docstring):
                fn.docstring = _first_sentence(fn.docstring)
                truncated_count += 1
        for cls in m.classes:
            if cls.docstring and cls.docstring != _first_sentence(cls.docstring):
                cls.docstring = _first_sentence(cls.docstring)
                truncated_count += 1
            for method in cls.methods:
                if method.docstring and method.docstring != _first_sentence(method.docstring):
                    method.docstring = _first_sentence(method.docstring)
                    truncated_count += 1

    if truncated_count > 0:
        logger.warning("truncated %d docstrings to fit token budget", truncated_count)

    if _current_tokens() <= max_tokens:
        return pruned

    # Stage 2: Drop constants
    dropped_constants = 0
    for m in pruned:
        dropped_constants += len(m.constants)
        m.constants = []
        for cls in m.classes:
            dropped_constants += len(cls.class_vars)
            cls.class_vars = []

    if dropped_constants > 0:
        logger.warning("dropped %d constants to fit token budget", dropped_constants)

    if _current_tokens() <= max_tokens:
        return pruned

    # Stage 3: Drop private methods and functions
    dropped_private = 0
    for m in pruned:
        orig_fns = len(m.functions)
        m.functions = [fn for fn in m.functions if not fn.is_private]
        dropped_private += orig_fns - len(m.functions)
        for cls in m.classes:
            orig_methods = len(cls.methods)
            cls.methods = [me for me in cls.methods if not me.is_private]
            dropped_private += orig_methods - len(cls.methods)

    if dropped_private > 0:
        logger.warning("dropped %d private symbols to fit token budget", dropped_private)

    if _current_tokens() <= max_tokens:
        return pruned

    # Stage 4: Drop entire modules (least-referenced first)
    ref_counts = _count_references(pruned)
    # Sort by reference count ascending
    pruned.sort(key=lambda m: ref_counts.get(m.path, 0))

    dropped_modules = 0
    while pruned and _current_tokens() > max_tokens:
        m = pruned.pop(0)
        dropped_modules += 1

    if dropped_modules > 0:
        logger.warning("dropped %d modules to fit token budget", dropped_modules)

    return pruned
