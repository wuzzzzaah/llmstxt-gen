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

_COMMENT = "comment"
_REQUIRED_PARAMETER = "required_parameter"
_OPTIONAL_PARAMETER = "optional_parameter"
_FORMAL_PARAMETER = "formal_parameter"
_IDENTIFIER = "identifier"
_METHOD_DEFINITION = "method_definition"
_METHOD_SIGNATURE = "method_signature"
_EXPORT_STATEMENT = "export_statement"
_FUNCTION_DECLARATION = "function_declaration"
_CLASS_DECLARATION = "class_declaration"
_INTERFACE_DECLARATION = "interface_declaration"
_TYPE_ALIAS_DECLARATION = "type_alias_declaration"
_LEXICAL_DECLARATION = "lexical_declaration"
_VARIABLE_DECLARATOR = "variable_declarator"
_ARROW_FUNCTION = "arrow_function"
_FUNCTION_EXPRESSION = "function_expression"
_ASYNC = "async"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_zod_type(node: Node, source: bytes) -> tuple[str, bool]:
    """Return (type_name, is_optional) for a Zod type expression."""
    is_optional = False
    type_name = "unknown"

    curr = node
    while curr.type == "call_expression":
        fn = curr.child_by_field_name("function")
        if fn and fn.type == "member_expression":
            prop = fn.child_by_field_name("property")
            if prop:
                name = _text(prop, source)
                if name == "optional":
                    is_optional = True
                elif name in (
                    "string",
                    "number",
                    "boolean",
                    "date",
                    "array",
                    "object",
                    "any",
                    "unknown",
                    "null",
                    "undefined",
                ):
                    type_name = name
            next_curr = fn.child_by_field_name("object")
            if next_curr is None:
                break
            curr = next_curr
        else:
            break

    if curr is not None and curr.type == "member_expression":
        prop = curr.child_by_field_name("property")
        if prop:
            name = _text(prop, source)
            if name in (
                "string",
                "number",
                "boolean",
                "date",
                "array",
                "object",
                "any",
                "unknown",
                "null",
                "undefined",
            ):
                type_name = name

    return type_name, is_optional


def _extract_zod_object_shape(node: Node, source: bytes) -> str | None:
    """Extract a condensed shape from a z.object({ ... }) call."""
    # node is expected to be the call_expression for z.object(...)
    args = node.child_by_field_name("arguments")
    if not args or not args.named_children:
        return None

    obj = args.named_children[0]
    if obj.type != "object":
        return None

    fields = []
    for child in obj.named_children:
        if child.type == "pair":
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node and val_node:
                key = _text(key_node, source)
                z_type, is_optional = _get_zod_type(val_node, source)
                fields.append(f"{key}{'?' if is_optional else ''}: {z_type}")

    if not fields:
        return "{}"
    return "{ " + ", ".join(fields) + " }"


def _leading_jsdoc(node: Node, source: bytes) -> str:
    """Return the JSDoc-style block comment immediately preceding ``node``."""
    prev = node.prev_sibling
    while prev is not None and prev.type in (_COMMENT,):
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
            _REQUIRED_PARAMETER,
            _OPTIONAL_PARAMETER,
            _FORMAL_PARAMETER,
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
                    is_optional=child.type == _OPTIONAL_PARAMETER,
                )
            )
        elif child.type == _IDENTIFIER:
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
        is_async=any(c.type == _ASYNC for c in node.children),
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
            if child.type in (_METHOD_DEFINITION, _METHOD_SIGNATURE):
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
                    is_async=any(c.type == _ASYNC for c in child.children),
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
                            if last.type == _IDENTIFIER:
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


def _extract_env_vars(node: Node, source: bytes, env_vars: dict[str, list[str]], path: str) -> None:
    """Recursively find process.env.VAR and process.env["VAR"] references."""
    if node.type == "member_expression":
        # process.env.VAR
        obj = node.child_by_field_name("object")
        prop = node.child_by_field_name("property")
        if obj and prop and prop.type == "property_identifier":
            if obj.type == "member_expression":
                inner_obj = obj.child_by_field_name("object")
                inner_prop = obj.child_by_field_name("property")
                if (
                    inner_obj
                    and inner_prop
                    and _text(inner_obj, source) == "process"
                    and _text(inner_prop, source) == "env"
                ):
                    var_name = _text(prop, source)
                    if var_name not in env_vars:
                        env_vars[var_name] = [path]
    elif node.type == "subscript_expression":
        # process.env["VAR"]
        obj = node.child_by_field_name("object")
        index = node.child_by_field_name("index")
        if obj and index and index.type == "string" and obj.type == "member_expression":
            inner_obj = obj.child_by_field_name("object")
            inner_prop = obj.child_by_field_name("property")
            if (
                inner_obj
                and inner_prop
                and _text(inner_obj, source) == "process"
                and _text(inner_prop, source) == "env"
            ):
                # Extract string content
                var_name = ""
                for child in index.named_children:
                    if child.type == "string_fragment":
                        var_name += _text(child, source)
                if var_name and var_name not in env_vars:
                    env_vars[var_name] = [path]

    for child in node.children:
        _extract_env_vars(child, source, env_vars, path)


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
    # Use rindex-like logic to find the LAST "app" segment, as absolute paths might
    # contain "app" earlier in the path (e.g. /app/tests/...).
    try:
        # list doesn't have rindex, so we find it manually
        app_idx = len(parts) - 1 - parts[::-1].index("app")
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
        if node.type == _EXPORT_STATEMENT:
            for child in node.named_children:
                if child.type == _FUNCTION_DECLARATION:
                    name_node = child.child_by_field_name("name")
                    if name_node is not None:
                        fn_name = _text(name_node, source)
                        exported_names.append(
                            (fn_name, child.start_point[0] + 1, _leading_jsdoc(node, source))
                        )
                elif child.type == _LEXICAL_DECLARATION:
                    for decl in child.named_children:
                        if decl.type == _VARIABLE_DECLARATOR:
                            n = decl.child_by_field_name("name")
                            v = decl.child_by_field_name("value")
                            if n is not None and v is not None and v.type in (
                                _ARROW_FUNCTION,
                                _FUNCTION_EXPRESSION,
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

        # Environment variable extraction
        _extract_env_vars(root, source, module.env_vars, module.path)

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
        if kind == _EXPORT_STATEMENT:
            for child in node.named_children:
                self._handle_top_level(
                    child, source, module, exported=True, doc_node=doc_node or node
                )
            return

        accept = exported or self.include_private
        outer = doc_node or node

        if kind == _FUNCTION_DECLARATION:
            fn = _parse_function_node(node, source, doc_node=outer)
            if accept:
                module.functions.append(fn)
        elif kind == _CLASS_DECLARATION:
            cls = _parse_class_node(node, source, self.include_private, doc_node=outer)
            if accept:
                module.classes.append(cls)
        elif kind in (_INTERFACE_DECLARATION, _TYPE_ALIAS_DECLARATION):
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else ""
            if accept:
                module.constants.append(
                    ParsedConstant(
                        name=name,
                        type_hint="interface" if kind == _INTERFACE_DECLARATION else "type",
                        value=_text(node, source),
                    )
                )
        elif kind == _LEXICAL_DECLARATION:
            for declarator in node.named_children:
                if declarator.type != _VARIABLE_DECLARATOR:
                    continue
                name_node = declarator.child_by_field_name("name")
                type_node = declarator.child_by_field_name("type")
                value_node = declarator.child_by_field_name("value")
                name = _text(name_node, source) if name_node else ""
                if value_node is not None and value_node.type in (
                    _ARROW_FUNCTION,
                    _FUNCTION_EXPRESSION,
                ):
                    fn = _parse_function_node(
                        value_node, source, name_override=name, doc_node=outer
                    )
                    if accept:
                        module.functions.append(fn)
                elif accept and name:
                    type_hint = _text(type_node, source).lstrip(":").strip() if type_node else ""
                    val_text = _text(value_node, source) if value_node else ""

                    if not type_hint and val_text.startswith("z."):
                        # Only extract shape if it doesn't use complex methods like .merge()
                        # in the top-level chain.
                        complex_methods = {
                            "merge",
                            "extend",
                            "pick",
                            "omit",
                            "partial",
                            "deepPartial",
                        }
                        is_complex = False
                        zod_curr: Node | None = value_node
                        while zod_curr is not None and zod_curr.type == "call_expression":
                            fn_node = zod_curr.child_by_field_name("function")
                            if fn_node is not None and fn_node.type == "member_expression":
                                prop = fn_node.child_by_field_name("property")
                                if prop and _text(prop, source) in complex_methods:
                                    is_complex = True
                                    break
                                zod_curr = fn_node.child_by_field_name("object")
                            else:
                                break

                        if not is_complex:
                            # Find the z.object call
                            z_obj_node = None
                            zod_curr = value_node
                            while zod_curr is not None and zod_curr.type == "call_expression":
                                fn_node = zod_curr.child_by_field_name("function")
                                if fn_node is not None and fn_node.type == "member_expression":
                                    prop = fn_node.child_by_field_name("property")
                                    if prop and _text(prop, source) == "object":
                                        obj = fn_node.child_by_field_name("object")
                                        if obj and _text(obj, source) == "z":
                                            z_obj_node = zod_curr
                                            break
                                    zod_curr = fn_node.child_by_field_name("object")
                                else:
                                    break

                            if z_obj_node:
                                shape = _extract_zod_object_shape(z_obj_node, source)
                                if shape:
                                    type_hint = shape

                    module.constants.append(
                        ParsedConstant(
                            name=name,
                            type_hint=type_hint,
                            value=val_text,
                        )
                    )
