"""Python parser backed by tree-sitter.

Extracts the module docstring, top-level functions, classes, and annotated
constants. Private symbols (``_leading_underscore``) are omitted unless the
caller opts in via :class:`PythonParser` ``include_private``.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_python
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

_PY_LANGUAGE = Language(tree_sitter_python.language())

_EXPRESSION_STATEMENT = "expression_statement"
_STRING = "string"
_IDENTIFIER = "identifier"
_TYPED_PARAMETER = "typed_parameter"
_DEFAULT_PARAMETER = "default_parameter"
_TYPED_DEFAULT_PARAMETER = "typed_default_parameter"
_LIST_SPLAT_PATTERN = "list_splat_pattern"
_DICTIONARY_SPLAT_PATTERN = "dictionary_splat_pattern"
_DECORATED_DEFINITION = "decorated_definition"
_DECORATOR = "decorator"
_FUNCTION_DEFINITION = "function_definition"
_CLASS_DEFINITION = "class_definition"
_ASSIGNMENT = "assignment"
_ASYNC = "async"
_IMPORT_STATEMENT = "import_statement"
_IMPORT_FROM_STATEMENT = "import_from_statement"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _child_by_field(node: Node, name: str) -> Node | None:
    return node.child_by_field_name(name)


def _extract_string_literal(node: Node, source: bytes) -> str:
    raw = _text(node, source).strip()
    for quote in ('"""', "'''", '"', "'"):
        if raw.startswith(quote) and raw.endswith(quote) and len(raw) >= 2 * len(quote):
            raw = raw[len(quote) : -len(quote)]
            break
    return raw


def _module_docstring(root: Node, source: bytes) -> str:
    for child in root.named_children:
        if child.type == _EXPRESSION_STATEMENT:
            expr = child.named_children[0] if child.named_children else None
            if expr is not None and expr.type == _STRING:
                return _extract_string_literal(expr, source)
        break
    return ""


def _function_docstring(func_node: Node, source: bytes) -> str:
    body = _child_by_field(func_node, "body")
    if body is None:
        return ""
    for child in body.named_children:
        if child.type == _EXPRESSION_STATEMENT:
            expr = child.named_children[0] if child.named_children else None
            if expr is not None and expr.type == _STRING:
                return _extract_string_literal(expr, source)
        break
    return ""


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if params_node is None:
        return []
    params: list[ParsedParameter] = []
    for child in params_node.named_children:
        kind = child.type
        if kind == _IDENTIFIER:
            params.append(ParsedParameter(name=_text(child, source)))
        elif kind == _TYPED_PARAMETER:
            name_node = child.named_children[0] if child.named_children else None
            type_node = _child_by_field(child, "type")
            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    type_hint=_text(type_node, source) if type_node else "",
                )
            )
        elif kind == _DEFAULT_PARAMETER:
            name_node = _child_by_field(child, "name")
            value_node = _child_by_field(child, "value")
            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    default=_text(value_node, source) if value_node else "",
                )
            )
        elif kind == _TYPED_DEFAULT_PARAMETER:
            name_node = _child_by_field(child, "name")
            type_node = _child_by_field(child, "type")
            value_node = _child_by_field(child, "value")
            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    type_hint=_text(type_node, source) if type_node else "",
                    default=_text(value_node, source) if value_node else "",
                )
            )
        elif kind in (_LIST_SPLAT_PATTERN, _DICTIONARY_SPLAT_PATTERN):
            prefix = "*" if kind == _LIST_SPLAT_PATTERN else "**"
            inner = child.named_children[0] if child.named_children else None
            base = _text(inner, source) if inner else ""
            params.append(ParsedParameter(name=f"{prefix}{base}"))
    return params


def _decorator_names(node: Node, source: bytes) -> list[str]:
    decorators: list[str] = []
    parent = node.parent
    if parent is None or parent.type != _DECORATED_DEFINITION:
        return decorators
    for child in parent.named_children:
        if child.type == _DECORATOR:
            inner = child.named_children[0] if child.named_children else None
            if inner is not None:
                decorators.append(_text(inner, source))
    return decorators


def _parse_function(node: Node, source: bytes) -> ParsedFunction:
    name_node = _child_by_field(node, "name")
    params_node = _child_by_field(node, "parameters")
    return_node = _child_by_field(node, "return_type")
    name = _text(name_node, source) if name_node else ""
    decorators = _decorator_names(node, source)
    return ParsedFunction(
        name=name,
        parameters=_parse_parameters(params_node, source),
        return_type=_text(return_node, source) if return_node else "",
        docstring=_function_docstring(node, source),
        line=node.start_point[0] + 1,
        is_async=any(c.type == _ASYNC for c in node.children),
        is_private=name.startswith("_") and not name.startswith("__"),
        is_property="property" in decorators,
        decorators=decorators,
    )


def _parse_class(node: Node, source: bytes, include_private: bool) -> ParsedClass:
    name_node = _child_by_field(node, "name")
    name = _text(name_node, source) if name_node else ""
    bases: list[str] = []
    superclasses = _child_by_field(node, "superclasses")
    if superclasses is not None:
        for child in superclasses.named_children:
            bases.append(_text(child, source))
    body = _child_by_field(node, "body")
    methods: list[ParsedFunction] = []
    class_vars: list[ParsedConstant] = []
    docstring = ""
    if body is not None:
        first = True
        for child in body.named_children:
            if first and child.type == _EXPRESSION_STATEMENT:
                expr = child.named_children[0] if child.named_children else None
                if expr is not None and expr.type == _STRING:
                    docstring = _extract_string_literal(expr, source)
            first = False
            target = child
            if child.type == _DECORATED_DEFINITION:
                inner = _child_by_field(child, "definition")
                if inner is not None:
                    target = inner
            if target.type == _FUNCTION_DEFINITION:
                fn = _parse_function(target, source)
                if include_private or not fn.is_private:
                    methods.append(fn)
            elif child.type == _EXPRESSION_STATEMENT:
                _maybe_class_var(child, source, class_vars)
    return ParsedClass(
        name=name,
        docstring=docstring,
        bases=bases,
        methods=methods,
        class_vars=class_vars,
        line=node.start_point[0] + 1,
    )


def _maybe_class_var(stmt: Node, source: bytes, out: list[ParsedConstant]) -> None:
    if not stmt.named_children:
        return
    inner = stmt.named_children[0]
    if inner.type != _ASSIGNMENT:
        return
    target = _child_by_field(inner, "left")
    type_node = _child_by_field(inner, "type")
    value_node = _child_by_field(inner, "right")
    if target is None:
        return
    # Module-level constants often lack type hints (e.g. __all__ = [...])
    if type_node is None and value_node is None:
        return

    out.append(
        ParsedConstant(
            name=_text(target, source),
            type_hint=_text(type_node, source) if type_node else "",
            value=_text(value_node, source) if value_node else "",
        )
    )


def _maybe_module_constant(stmt: Node, source: bytes, out: list[ParsedConstant]) -> None:
    _maybe_class_var(stmt, source, out)


_FASTAPI_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


def _extract_python_routes(node: Node, source: bytes) -> list[ParsedRoute]:
    """Extract FastAPI and Flask routes from a decorated definition."""
    if node.type != _DECORATED_DEFINITION:
        return []

    routes: list[ParsedRoute] = []
    func_node = _child_by_field(node, "definition")
    if not func_node or func_node.type != _FUNCTION_DEFINITION:
        return []

    handler_name = ""
    name_node = _child_by_field(func_node, "name")
    if name_node:
        handler_name = _text(name_node, source)

    docstring = _function_docstring(func_node, source)

    for decorator in node.named_children:
        if decorator.type != _DECORATOR:
            continue

        call = decorator.named_children[0] if decorator.named_children else None
        if not call or call.type != "call":
            continue

        fn = _child_by_field(call, "function")
        if not fn or fn.type != "attribute":
            continue

        # obj.attr (e.g. app.get or router.post)
        attr_node = _child_by_field(fn, "attribute")
        if not attr_node:
            continue

        method_name = _text(attr_node, source)
        args = _child_by_field(call, "arguments")
        if not args:
            continue

        # Extract path (usually first positional argument or 'path' kwarg)
        path = ""
        named_args = args.named_children
        for i, arg in enumerate(named_args):
            if i == 0 and arg.type == _STRING:
                path = _extract_string_literal(arg, source)
                break
            if arg.type == "keyword_argument":
                kw_name = _child_by_field(arg, "name")
                if kw_name and _text(kw_name, source) == "path":
                    kw_val = _child_by_field(arg, "value")
                    if kw_val and kw_val.type == _STRING:
                        path = _extract_string_literal(kw_val, source)
                        break

        if method_name in _FASTAPI_METHODS:
            routes.append(
                ParsedRoute(
                    method=method_name.upper(),
                    path=path,
                    handler=handler_name,
                    line=decorator.start_point[0] + 1,
                    docstring=docstring,
                )
            )
        elif method_name == "route":
            # Flask style: @app.route("/path", methods=["GET", "POST"])
            methods = ["GET"]  # Default Flask method
            for arg in named_args:
                if arg.type == "keyword_argument":
                    kw_name = _child_by_field(arg, "name")
                    if kw_name and _text(kw_name, source) == "methods":
                        value = _child_by_field(arg, "value")
                        if value and value.type in ("list", "tuple"):
                            methods = []
                            for item in value.named_children:
                                if item.type == _STRING:
                                    methods.append(_extract_string_literal(item, source).upper())

            for m in methods:
                routes.append(
                    ParsedRoute(
                        method=m,
                        path=path,
                        handler=handler_name,
                        line=decorator.start_point[0] + 1,
                        docstring=docstring,
                    )
                )

    return routes


def _extract_env_vars(node: Node, source: bytes, env_vars: dict[str, list[str]], path: str) -> None:
    """Recursively find os.environ[VAR], os.environ.get(VAR), os.getenv(VAR)."""
    if node.type == "subscript":
        # os.environ["VAR"]
        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "attribute":
            obj = value_node.child_by_field_name("object")
            attr = value_node.child_by_field_name("attribute")
            if (
                obj
                and attr
                and _text(obj, source) == "os"
                and _text(attr, source) == "environ"
            ):
                subscript = node.child_by_field_name("subscript")
                if subscript and subscript.type == "string":
                    var_name = _extract_string_literal(subscript, source)
                    if var_name and var_name not in env_vars:
                        env_vars[var_name] = [path]
    elif node.type == "call":
        # os.environ.get("VAR") or os.getenv("VAR")
        fn_node = node.child_by_field_name("function")
        if fn_node and fn_node.type == "attribute":
            obj = fn_node.child_by_field_name("object")
            attr = fn_node.child_by_field_name("attribute")
            if obj and attr:
                obj_text = _text(obj, source)
                attr_text = _text(attr, source)
                is_env_get = False
                if obj_text == "os" and attr_text == "getenv":
                    is_env_get = True
                elif attr_text == "get" and obj.type == "attribute":
                    inner_obj = obj.child_by_field_name("object")
                    inner_attr = obj.child_by_field_name("attribute")
                    if (
                        inner_obj
                        and inner_attr
                        and _text(inner_obj, source) == "os"
                        and _text(inner_attr, source) == "environ"
                    ):
                        is_env_get = True

                if is_env_get:
                    args = node.child_by_field_name("arguments")
                    if args and args.named_children:
                        first_arg = args.named_children[0]
                        if first_arg.type == "string":
                            var_name = _extract_string_literal(first_arg, source)
                            if var_name and var_name not in env_vars:
                                env_vars[var_name] = [path]

    for child in node.children:
        _extract_env_vars(child, source, env_vars, path)


class PythonParser(BaseParser):
    """Parse Python source via tree-sitter."""

    language = "python"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_PY_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="python",
            docstring=_module_docstring(root, source),
        )

        for child in root.named_children:
            if child.type == _IMPORT_STATEMENT:
                for named_child in child.named_children:
                    if named_child.type == "dotted_name":
                        module.imports.append(_text(named_child, source))
                    elif named_child.type == "aliased_import":
                        dotted = named_child.child_by_field_name("name")
                        if dotted:
                            module.imports.append(_text(dotted, source))
                continue
            if child.type == _IMPORT_FROM_STATEMENT:
                module_node = child.child_by_field_name("module_name")
                if module_node:
                    module.imports.append(_text(module_node, source))
                else:
                    # check for relative_import
                    for named_child in child.named_children:
                        if named_child.type == "relative_import":
                            module.imports.append(_text(named_child, source))
                            break
                continue

            target = child
            if child.type == _DECORATED_DEFINITION:
                module.routes.extend(_extract_python_routes(child, source))
                inner = _child_by_field(child, "definition")
                if inner is not None:
                    target = inner
            if target.type == _FUNCTION_DEFINITION:
                fn = _parse_function(target, source)
                if self.include_private or not fn.is_private:
                    module.functions.append(fn)
            elif target.type == _CLASS_DEFINITION:
                cls = _parse_class(target, source, self.include_private)
                if self.include_private or not cls.name.startswith("_"):
                    module.classes.append(cls)
            elif child.type == _EXPRESSION_STATEMENT:
                _maybe_module_constant(child, source, module.constants)

        _extract_env_vars(root, source, module.env_vars, module.path)

        return module
