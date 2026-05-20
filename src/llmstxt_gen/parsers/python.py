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
    return raw.strip()


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
    if target is None or type_node is None:
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
            target = child
            if child.type == _DECORATED_DEFINITION:
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

        return module
