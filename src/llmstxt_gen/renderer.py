"""Render parsed modules to llms.txt and llms-full.txt Markdown."""

from __future__ import annotations

import re

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.parsers.base import ParsedFunction, ParsedModule, ParsedRoute

_ANCHOR_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _ANCHOR_RE.sub("-", text.lower()).strip("-")


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    text = text.strip().splitlines()[0]
    if "." in text:
        text = text.split(".", 1)[0] + "."
    return text


def _format_params(fn: ParsedFunction) -> str:
    bits: list[str] = []
    for p in fn.parameters:
        chunk = p.name + ("?" if p.is_optional else "")
        if p.type_hint:
            chunk += f": {p.type_hint}"
        if p.default:
            chunk += f" = {p.default}"
        bits.append(chunk)
    return ", ".join(bits)


def _format_signature(fn: ParsedFunction) -> str:
    prefix = "async " if fn.is_async else ""
    sig = f"{prefix}{fn.name}({_format_params(fn)})"
    if fn.return_type:
        sig += f" -> {fn.return_type}"
    return sig


def _path_key(path: str) -> str:
    """Return a display key for a module — the relative path without extension.

    Using the full path instead of the bare filename stem avoids ambiguity in
    projects where many files share the same name (e.g. Next.js ``page.tsx``).
    """
    from pathlib import PurePosixPath

    return str(PurePosixPath(path).with_suffix(""))


def render_summary(modules: list[ParsedModule], config: LlmsTxtConfig) -> str:
    """Render a spec-compliant ``llms.txt`` summary document."""
    out: list[str] = [f"# {config.name or 'project'}", ""]
    if config.description:
        out.extend([f"> {config.description}", ""])

    out.append("## Modules")
    out.append("")
    for module in modules:
        anchor = _slug(module.path)
        key = _path_key(module.path)
        desc = _first_sentence(module.docstring) or _first_sentence(_module_fallback(module))
        out.append(f"- [{key}]({config.output_full}#{anchor}): {desc}".rstrip())
    out.append("")
    return "\n".join(out)


def _module_fallback(module: ParsedModule) -> str:
    if module.classes:
        return f"Defines {', '.join(c.name for c in module.classes)}."
    if module.functions:
        return f"Provides {', '.join(f.name for f in module.functions)}."
    return ""


def render_full(modules: list[ParsedModule], config: LlmsTxtConfig) -> str:
    """Render the detailed ``llms-full.txt`` document."""
    out: list[str] = [f"# {config.name or 'project'}", ""]
    if config.description:
        out.extend([f"> {config.description}", ""])

    for module in modules:
        anchor = _slug(module.path)
        out.append(f"## {module.path}")
        out.append(f'<a id="{anchor}"></a>')
        out.append("")
        if module.docstring:
            out.extend([module.docstring, ""])

        if module.functions:
            out.append("### Functions")
            out.append("")
            for fn in module.functions:
                out.append(f"#### `{_format_signature(fn)}`")
                if fn.decorators:
                    out.append(f"_Decorators: {', '.join('@' + d for d in fn.decorators)}_")
                if fn.docstring:
                    out.extend(["", fn.docstring])
                out.append("")

        if module.classes:
            out.append("### Classes")
            out.append("")
            for cls in module.classes:
                bases = f"({', '.join(cls.bases)})" if cls.bases else ""
                out.append(f"#### `{cls.name}{bases}`")
                if cls.docstring:
                    out.extend(["", cls.docstring])
                if cls.methods:
                    out.append("")
                    out.append("##### Methods")
                    out.append("")
                    for method in cls.methods:
                        out.append(f"###### `{_format_signature(method)}`")
                        if method.docstring:
                            out.extend(["", method.docstring])
                        out.append("")
                out.append("")

        if module.constants:
            out.append("### Constants")
            out.append("")
            for const in module.constants:
                line = f"- `{const.name}`"
                if const.type_hint:
                    line += f": `{const.type_hint}`"
                elif const.value.startswith("z.") or ".partial(" in const.value:
                    # Fallback for Zod schemas that weren't condensed into type_hint
                    val = " ".join(const.value.splitlines()).strip()
                    if len(val) > 120:
                        val = val[:117] + "..."
                    line += f": `{val}`"
                out.append(line)
            out.append("")

        if module.routes:
            out.append("### Routes")
            out.append("")
            for route in module.routes:
                out.append(_format_route(route))
            out.append("")

    return "\n".join(out)


def _format_route(route: ParsedRoute) -> str:
    """Render a single route as a Markdown list item."""
    line = f"- `{route.method} {route.path}`"
    if route.handler and route.handler not in ("default",):
        line += f" → `{route.handler}`"
    if route.docstring:
        line += f" — {route.docstring}"
    return line
