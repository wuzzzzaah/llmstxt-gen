"""Render parsed modules to llms.txt and llms-full.txt Markdown."""

from __future__ import annotations

import json
import re
from pathlib import Path

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
        desc = _first_sentence(module.docstring) or _first_sentence(_module_fallback(module, config))
        out.append(f"- [{key}]({config.output_full}#{anchor}): {desc}".rstrip())
    out.append("")
    return "\n".join(out)


def _module_fallback(module: ParsedModule, config: LlmsTxtConfig) -> str:
    if not config.smart_summaries:
        return _legacy_fallback(module)

    # 1. Next.js Page component
    if module.path.endswith(("page.tsx", "page.jsx", "page.ts", "page.js")):
        for route in module.routes:
            if route.handler == "default" and route.method == "GET":
                return f"Page component at {route.path}."

    # 2. HTTP Routes
    if module.routes:
        return "Defines HTTP routes."

    # 3. Filename heuristics
    stem = Path(module.path).stem.lower()
    mapping = {
        "models": "Data models.",
        "utils": "Utility functions.",
        "helpers": "Utility functions.",
        "types": "Type definitions.",
        "schemas": "Schema definitions.",
        "routes": "HTTP route handlers.",
        "constants": "Module constants.",
        "config": "Configuration settings.",
    }
    if stem in mapping:
        return mapping[stem]

    # 4. Exported docstrings
    for cls in module.classes:
        if cls.docstring:
            return cls.docstring
    for fn in module.functions:
        if fn.docstring:
            return fn.docstring

    # 5. __all__ heuristic
    for const in module.constants:
        if const.name == "__all__":
            val = const.value.strip("[]() ").replace("'", "").replace('"', "")
            items = [i.strip() for i in val.split(",") if i.strip()]
            if items:
                return f"Provides {', '.join(items)}."

    return _legacy_fallback(module)


def _legacy_fallback(module: ParsedModule) -> str:
    if module.classes:
        return f"Defines {', '.join(c.name for c in module.classes)}."
    if module.functions:
        return f"Provides {', '.join(f.name for f in module.functions)}."
    return ""


def render_mini(modules: list[ParsedModule], config: LlmsTxtConfig) -> str:
    """Render a signatures-only ``llms-mini.txt`` document."""
    out: list[str] = [config.name or "project"]

    for module in modules:
        out.append(module.path)
        out.append("")

        if module.functions:
            for fn in module.functions:
                out.append(_format_signature(fn))
            out.append("")

        if module.classes:
            for cls in module.classes:
                out.append(cls.name)
                out.append("")
                if cls.methods:
                    for method in cls.methods:
                        out.append(_format_signature(method))
                    out.append("")

    return "\n".join(out).strip() + "\n"


def render_full(modules: list[ParsedModule], config: LlmsTxtConfig) -> str:
    """Render the detailed ``llms-full.txt`` document."""
    out: list[str] = [f"# {config.name or 'project'}", ""]
    if config.description:
        out.extend([f"> {config.description}", ""])

    # Aggregate environment variables
    all_env_vars: dict[str, set[str]] = {}
    for module in modules:
        for var, paths in module.env_vars.items():
            all_env_vars.setdefault(var, set()).update(paths)

    if all_env_vars:
        out.append("## Environment Variables")
        out.append("")
        out.append("| Variable | Files |")
        out.append("|---|---|")
        for var in sorted(all_env_vars.keys()):
            files = ", ".join(f"`{p}`" for p in sorted(all_env_vars[var]))
            out.append(f"| `{var}` | {files} |")
        out.append("")

    for module in modules:
        anchor = _slug(module.path)
        out.append(f"## {module.path}")
        out.append(f'<a id="{anchor}"></a>')

        if config.emit_frontmatter:
            out.append("```yaml")
            out.append(f"language: {module.language}")
            exports = sorted(
                {f.name for f in module.functions}
                | {c.name for c in module.classes}
                | {cn.name for cn in module.constants}
            )
            if exports:
                out.append(f"exports: {json.dumps(exports)}")
            if module.imports:
                imports = sorted(set(module.imports))
                out.append(f"imports: {json.dumps(imports)}")
            if module.routes:
                routes = sorted({f"{r.method} {r.path}" for r in module.routes})
                out.append(f"routes: {json.dumps(routes)}")
            out.append("```")

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
