"""JavaScript/TypeScript parser backed by tree-sitter.

Extracts exported functions, classes, type aliases, interfaces, constants,
and HTTP route handlers (Express.js and Next.js App Router conventions).
Non-exported symbols are skipped unless ``include_private`` is set on the
parser.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from llmstxt_gen.parsers.base import (
    BaseParser,
    ParsedClass,
    ParsedConstant,
    ParsedFunction,
    ParsedModule,
    ParsedParameter,
    ParsedRoute,
)
from llmstxt_gen.walker import SourceFile

_JS_LANGUAGE = Language(tree_sitter_javascript.language())
_TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
_TSX_LANGUAGE = Language(tree_sitter_typescript.language_tsx())


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _leading_jsdoc(node: Node, source: bytes) -> str:
    """Return the JSDoc-style block comment immediately preceding ``node``."""
    prev = node.prev_sibling
    while prev is not None and prev.type in ("comment",):
        text = _text(prev, source).strip()
        if text.startswith("/**"):
            stripped = text[3:-2] if text.endswith("*/") else text[3:]
            lines = [ln.strip().lstrip("*").strip() for ln in stripped.splitlines()]
            return "\n".join(ln for ln in lines if ln).strip()
        prev = prev.prev_sibling
    return ""


def _parse_ts_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if params_node is None:
        return []
    out: list[ParsedParameter] = []
    for child in params_node.named_children:
        if child.type in (
            "required_parameter",
            "optional_parameter",
            "formal_parameter",
        ):
            name = ""
            type_hint = ""
            default = ""
            pattern = child.child_by_field_name("pattern")
            if pattern is not None:
                name = _text(pattern, source)
            type_ann = child.child_by_field_name("type")
            if type_ann is not None:
                type_hint = _text(type_ann, source).lstrip(":").strip()
            value = child.child_by_field_name("value")
            if value is not None:
                default = _text(value, source)
            out.append(
                ParsedParameter(
                    name=name,
                    type_hint=type_hint,
                    default=default,
                    is_optional=child.type == "optional_parameter",
                )
            )
        elif child.type == "identifier":
            out.append(ParsedParameter(name=_text(child, source)))
    return out


def _function_return_type(node: Node, source: bytes) -> str:
    ret = node.child_by_field_name("return_type")
    if ret is None:
        return ""
    return _text(ret, source).lstrip(":").strip()


def _parse_function_node(
    node: Node, source: bytes, name_override: str = "", doc_node: Node | None = None
) -> ParsedFunction:
    name_node = node.child_by_field_name("name")
    name = name_override or (_text(name_node, source) if name_node else "")
    params = _parse_ts_parameters(node.child_by_field_name("parameters"), source)
    return ParsedFunction(
        name=name,
        parameters=params,
        return_type=_function_return_type(node, source),
        docstring=_leading_jsdoc(doc_node or node, source),
        line=node.start_point[0] + 1,
        is_async=any(c.type == "async" for c in node.children),
        is_private=name.startswith("_"),
    )


def _parse_class_node(
    node: Node, source: bytes, include_private: bool, doc_node: Node | None = None
) -> ParsedClass:
    name_node = node.child_by_field_name("name")
    name = _text(name_node, source) if name_node else ""
    bases: list[str] = []
    heritage = node.child_by_field_name("heritage")
    if heritage is not None:
        for child in heritage.named_children:
            bases.append(_text(child, source))
    body = node.child_by_field_name("body")
    methods: list[ParsedFunction] = []
    if body is not None:
        for child in body.named_children:
            if child.type in ("method_definition", "method_signature"):
                fn_name_node = child.child_by_field_name("name")
                fn_name = _text(fn_name_node, source) if fn_name_node else ""
                fn = ParsedFunction(
                    name=fn_name,
                    parameters=_parse_ts_parameters(
                        child.child_by_field_name("parameters"), source
                    ),
                    return_type=_function_return_type(child, source),
                    docstring=_leading_jsdoc(child, source),
                    line=child.start_point[0] + 1,
                    is_async=any(c.type == "async" for c in child.children),
                    is_private=fn_name.startswith("_") or fn_name.startswith("#"),
                )
                if include_private or not fn.is_private:
                    methods.append(fn)
    return ParsedClass(
        name=name,
        docstring=_leading_jsdoc(doc_node or node, source),
        bases=bases,
        methods=methods,
        line=node.start_point[0] + 1,
    )


_EXPRESS_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "all"})
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


def _extract_express_routes(root: Node, source: bytes) -> list[ParsedRoute]:
    """Walk the AST and collect Express-style ``app.METHOD(path, handler)`` calls."""
    routes: list[ParsedRoute] = []

    def _walk(node: Node) -> None:
        if node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            args_node = node.child_by_field_name("arguments")
            if fn_node is not None and fn_node.type == "member_expression" and args_node is not None:
                prop = fn_node.child_by_field_name("property")
                method_text = _text(prop, source) if prop is not None else ""
                if method_text.lower() in _EXPRESS_METHODS:
                    # First argument should be the path string
                    arg_children = [c for c in args_node.named_children]
                    if arg_children:
                        path_node = arg_children[0]
                        raw = _text(path_node, source)
                        # Strip surrounding quotes
                        if (raw.startswith('"') and raw.endswith('"')) or (
                            raw.startswith("'") and raw.endswith("'")
                        ):
                            raw = raw[1:-1]
                        # Resolve handler name if it's an identifier
                        handler = ""
                        if len(arg_children) >= 2:
                            last = arg_children[-1]
                            if last.type == "identifier":
                                handler = _text(last, source)
                        routes.append(
                            ParsedRoute(
                                method=method_text.upper(),
                                path=raw,
                                handler=handler,
                                line=node.start_point[0] + 1,
                                docstring=_leading_jsdoc(node, source),
                            )
                        )
        for child in node.children:
            _walk(child)

    _walk(root)
    return routes


def _infer_nextjs_routes(
    root: Node, source: bytes, file_path: Any
) -> list[ParsedRoute]:
    """Infer Next.js App Router routes from the file path and exported HTTP-verb functions.

    * ``route.ts`` / ``route.js`` files: each exported function named after an
      HTTP verb (GET, POST, …) becomes a route.
    * ``page.tsx`` / ``page.jsx`` / ``page.ts`` / ``page.js`` files: the file
      itself represents a ``GET`` page render route.
    """
    from pathlib import PurePosixPath

    routes: list[ParsedRoute] = []
    stem = file_path.stem.lower()
    suffix = file_path.suffix.lower()
    if stem not in ("route", "page"):
        return routes

    # Derive the URL path from the file path by stripping the filename and
    # the leading "app" segment if present.
    parts = list(PurePosixPath(str(file_path)).parts)
    # Remove the filename
    parts = parts[:-1]
    # Strip everything up to and including the "app" directory (Next.js App
    # Router root).  Works for both relative and absolute paths.
    try:
        app_idx = parts.index("app")
        parts = parts[app_idx + 1 :]
    except ValueError:
        pass
    # Remove dynamic-segment brackets to make a clean path representation
    url_path = "/" + "/".join(parts) if parts else "/"

    if stem == "page" and suffix in (".tsx", ".jsx", ".ts", ".js"):
        routes.append(
            ParsedRoute(
                method="GET",
                path=url_path,
                handler="default",
                line=1,
                docstring="Next.js page component.",
            )
        )
        return routes

    # route.ts — look for exported HTTP-verb function declarations
    exported_names: list[tuple[str, int, str]] = []  # (name, line, docstring)

    def _collect_exports(node: Node) -> None:
        if node.type == "export_statement":
            for child in node.named_children:
                if child.type == "function_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node is not None:
                        fn_name = _text(name_node, source)
                        exported_names.append(
                            (fn_name, child.start_point[0] + 1, _leading_jsdoc(node, source))
                        )
                elif child.type == "lexical_declaration":
                    for decl in child.named_children:
                        if decl.type == "variable_declarator":
                            n = decl.child_by_field_name("name")
                            v = decl.child_by_field_name("value")
                            if n is not None and v is not None and v.type in (
                                "arrow_function",
                                "function_expression",
                            ):
                                exported_names.append(
                                    (
                                        _text(n, source),
                                        decl.start_point[0] + 1,
                                        _leading_jsdoc(node, source),
                                    )
                                )
        for child in node.children:
            _collect_exports(child)

    _collect_exports(root)
    for fn_name, line, doc in exported_names:
        if fn_name.upper() in _HTTP_METHODS:
            routes.append(
                ParsedRoute(
                    method=fn_name.upper(),
                    path=url_path,
                    handler=fn_name,
                    line=line,
                    docstring=doc,
                )
            )
    return routes


class TypeScriptParser(BaseParser):
    """Parse JavaScript and TypeScript via tree-sitter."""

    language = "typescript"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._js_parser: Any = Parser(_JS_LANGUAGE)
        self._ts_parser: Any = Parser(_TS_LANGUAGE)
        self._tsx_parser: Any = Parser(_TSX_LANGUAGE)

    def _parser_for(self, source_file: SourceFile) -> Any:
        suffix = source_file.path.suffix.lower()
        if suffix == ".tsx":
            return self._tsx_parser
        if suffix in (".ts",):
            return self._ts_parser
        return self._js_parser

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        parser = self._parser_for(source_file)
        tree = parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language=source_file.language,
            docstring=_leading_jsdoc(root.named_children[0], source) if root.named_children else "",
        )

        for child in root.named_children:
            self._handle_top_level(child, source, module, exported=False)

        # Route extraction: Express and Next.js App Router
        module.routes.extend(_extract_express_routes(root, source))
        module.routes.extend(_infer_nextjs_routes(root, source, source_file.path))

        return module

    def _handle_top_level(
        self,
        node: Node,
        source: bytes,
        module: ParsedModule,
        exported: bool,
        doc_node: Node | None = None,
    ) -> None:
        kind = node.type
        if kind == "export_statement":
            for child in node.named_children:
                self._handle_top_level(
                    child, source, module, exported=True, doc_node=doc_node or node
                )
            return

        accept = exported or self.include_private
        outer = doc_node or node

        if kind == "function_declaration":
            fn = _parse_function_node(node, source, doc_node=outer)
            if accept:
                module.functions.append(fn)
        elif kind == "class_declaration":
            cls = _parse_class_node(node, source, self.include_private, doc_node=outer)
            if accept:
                module.classes.append(cls)
        elif kind in ("interface_declaration", "type_alias_declaration"):
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else ""
            if accept:
                module.constants.append(
                    ParsedConstant(
                        name=name,
                        type_hint="interface" if kind == "interface_declaration" else "type",
                        value=_text(node, source),
                    )
                )
        elif kind == "lexical_declaration":
            for declarator in node.named_children:
                if declarator.type != "variable_declarator":
                    continue
                name_node = declarator.child_by_field_name("name")
                type_node = declarator.child_by_field_name("type")
                value_node = declarator.child_by_field_name("value")
                name = _text(name_node, source) if name_node else ""
                if value_node is not None and value_node.type in (
                    "arrow_function",
                    "function_expression",
                ):
                    fn = _parse_function_node(
                        value_node, source, name_override=name, doc_node=outer
                    )
                    if accept:
                        module.functions.append(fn)
                elif accept and name:
                    module.constants.append(
                        ParsedConstant(
                            name=name,
                            type_hint=(
                                _text(type_node, source).lstrip(":").strip() if type_node else ""
                            ),
                            value=_text(value_node, source) if value_node else "",
                        )
                    )
