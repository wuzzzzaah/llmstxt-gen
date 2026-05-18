"""JavaScript/TypeScript parser backed by tree-sitter.

Extracts exported functions, classes, type aliases, interfaces, and
constants. Non-exported symbols are skipped unless ``include_private`` is
set on the parser.
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
            out.append(ParsedParameter(name=name, type_hint=type_hint, default=default))
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


class TypeScriptParser(BaseParser):
    """Parse JavaScript and TypeScript via tree-sitter."""

    language = "typescript"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private

    def _language_for(self, source_file: SourceFile) -> Language:
        suffix = source_file.path.suffix.lower()
        if suffix == ".tsx":
            return _TSX_LANGUAGE
        if suffix in (".ts",):
            return _TS_LANGUAGE
        return _JS_LANGUAGE

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        parser: Any = Parser(self._language_for(source_file))
        tree = parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language=source_file.language,
            docstring=_leading_jsdoc(root.named_children[0], source)
            if root.named_children
            else "",
        )

        for child in root.named_children:
            self._handle_top_level(child, source, module, exported=False)
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
