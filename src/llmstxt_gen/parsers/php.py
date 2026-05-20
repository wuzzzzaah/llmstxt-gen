"""PHP parser backed by tree-sitter.

Extracts PHPDoc comments, public/protected classes, interfaces, traits, enums,
and their members.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_php
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

_PHP_LANGUAGE = Language(tree_sitter_php.language_php())

_COMMENT = "comment"
_LINE_COMMENT = "line_comment"
_TEXT_INTERPOLATION = "text_interpolation"
_INTERFACE_DECLARATION = "interface_declaration"
_VISIBILITY_MODIFIER = "visibility_modifier"
_SIMPLE_PARAMETER = "simple_parameter"
_VARIADIC_PARAMETER = "variadic_parameter"
_COLON = ":"
_PROPERTY_ELEMENT = "property_element"
_CONST_ELEMENT = "const_element"
_NAME = "name"
_EQUAL = "="
_PHP_TAG = "php_tag"
_NAMESPACE_DEFINITION = "namespace_definition"
_FUNCTION_DEFINITION = "function_definition"
_CLASS_DECLARATION = "class_declaration"
_TRAIT_DECLARATION = "trait_declaration"
_ENUM_DECLARATION = "enum_declaration"
_BASE_CLAUSE = "base_clause"
_CLASS_INTERFACE_CLAUSE = "class_interface_clause"
_ENUM_DECLARATION_LIST = "enum_declaration_list"
_METHOD_DECLARATION = "method_declaration"
_PROPERTY_DECLARATION = "property_declaration"
_CONST_DECLARATION = "const_declaration"
_ENUM_CASE = "enum_case"


def _text(node: Node | None, source: bytes) -> str:
    if not node:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_phpdoc(node: Node, source: bytes) -> str:
    """Extract PHPDoc comment immediately preceding the node."""
    prev = node.prev_sibling
    # In PHP, PHPDoc comments are typically block comments starting with /**
    while prev and prev.type in (_COMMENT, _LINE_COMMENT, _TEXT_INTERPOLATION):
        if prev.type == _COMMENT:
            text = _text(prev, source).strip()
            if text.startswith("/**"):
                # It's a PHPDoc
                lines = text[3:-2].strip().splitlines()
                processed = []
                for line in lines:
                    line = line.strip().lstrip("*").strip()
                    processed.append(line)
                return "\n".join(processed).strip()
        prev = prev.prev_sibling
    return ""


def _is_exported(node: Node, source: bytes, parent_type: str | None = None) -> bool:
    """Check if a node is public or unscoped (default).

    In interfaces, members are public by default.
    """
    if parent_type == _INTERFACE_DECLARATION:
        return True

    # Find visibility_modifier node
    visibility = None
    for child in node.children:
        if child.type == _VISIBILITY_MODIFIER:
            visibility = child
            break

    if not visibility:
        # Unscoped in PHP is public
        return True

    text = _text(visibility, source)
    return text == "public"


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if not params_node:
        return []
    params = []
    for child in params_node.named_children:
        if child.type in (_SIMPLE_PARAMETER, _VARIADIC_PARAMETER):
            type_node = child.child_by_field_name("type")
            name_node = child.child_by_field_name("name")
            default_node = child.child_by_field_name("default_value")

            name = _text(name_node, source)
            if child.type == _VARIADIC_PARAMETER:
                name = "..." + name

            params.append(
                ParsedParameter(
                    name=name,
                    type_hint=_text(type_node, source),
                    default=_text(default_node, source),
                )
            )
    return params


def _parse_method(node: Node, source: bytes, parent_type: str | None = None) -> ParsedFunction:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    return_type_node = node.child_by_field_name("return_type")

    return_type = ""
    if return_type_node:
        return_type = _text(return_type_node, source)
    else:
        # Fallback for older tree-sitter or different structure
        found_colon = False
        for child in node.children:
            if child.type == _COLON:
                found_colon = True
            elif found_colon and child.is_named:
                return_type = _text(child, source)
                break

    return ParsedFunction(
        name=_text(name_node, source),
        parameters=_parse_parameters(params_node, source),
        return_type=return_type,
        docstring=_get_phpdoc(node, source),
        line=node.start_point[0] + 1,
        is_private=not _is_exported(node, source, parent_type),
    )


def _parse_property(node: Node, source: bytes) -> list[ParsedConstant]:
    # property_declaration can have multiple variables: public $a, $b;
    # It can also have a type
    type_node = node.child_by_field_name("type")
    type_hint = _text(type_node, source)
    constants = []
    for child in node.named_children:
        if child.type == _PROPERTY_ELEMENT:
            name_node = child.child_by_field_name("name")
            default_node = child.child_by_field_name("default_value")
            constants.append(
                ParsedConstant(
                    name=_text(name_node, source),
                    type_hint=type_hint,
                    value=_text(default_node, source),
                )
            )
    return constants


def _parse_const(node: Node, source: bytes) -> list[ParsedConstant]:
    # const_declaration can have multiple elements
    constants = []
    for child in node.named_children:
        if child.type == _CONST_ELEMENT:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")

            # Tree-sitter PHP might not expose fields for const_element
            if not name_node:
                for c in child.named_children:
                    if c.type == _NAME:
                        name_node = c
                    elif not value_node and c.type not in (_NAME, _EQUAL):
                        value_node = c

            constants.append(
                ParsedConstant(
                    name=_text(name_node, source),
                    value=_text(value_node, source),
                )
            )
    return constants


class PHPParser(BaseParser):
    """Parse PHP source via tree-sitter."""

    language = "php"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_PHP_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="php",
        )

        # Look for first PHPDoc comment
        for child in root.children:
            if child.type == _COMMENT and _text(child, source).startswith("/**"):
                text = _text(child, source).strip()
                lines = text[3:-2].strip().splitlines()
                processed = []
                for line in lines:
                    line = line.strip().lstrip("*").strip()
                    processed.append(line)
                module.docstring = "\n".join(processed).strip()
                break
            if child.type not in (_PHP_TAG, _TEXT_INTERPOLATION, _COMMENT, _LINE_COMMENT):
                break

        self._parse_nodes(root, source, module)

        return module

    def _parse_nodes(self, node: Node, source: bytes, module: ParsedModule) -> None:
        for child in node.named_children:
            if child.type == _NAMESPACE_DEFINITION:
                body = child.child_by_field_name("body")
                if body:
                    self._parse_nodes(body, source, module)
                else:
                    # namespace MyNamespace; style - everything after is in namespace
                    pass
            elif child.type == _FUNCTION_DEFINITION:
                fn = _parse_method(child, source)
                if self.include_private or not fn.is_private:
                    module.functions.append(fn)
            elif child.type in (
                _CLASS_DECLARATION,
                _INTERFACE_DECLARATION,
                _TRAIT_DECLARATION,
                _ENUM_DECLARATION,
            ):
                self._parse_class(child, source, module)

    def _parse_class(self, node: Node, source: bytes, module: ParsedModule) -> None:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source)

        is_exported = _is_exported(node, source)

        bases = []
        if node.type != _INTERFACE_DECLARATION:
            for child in node.named_children:
                if child.type in (_BASE_CLAUSE, _CLASS_INTERFACE_CLAUSE):
                    for c in child.named_children:
                        if c.type == _NAME:
                            bases.append(_text(c, source))

        cls = ParsedClass(
            name=name,
            docstring=_get_phpdoc(node, source),
            bases=bases,
            line=node.start_point[0] + 1,
        )

        body = node.child_by_field_name("body")
        if not body:
            # For enums, it might be enum_declaration_list
            for c in node.children:
                if c.type == _ENUM_DECLARATION_LIST:
                    body = c
                    break

        if body:
            for member in body.named_children:
                if member.type == _METHOD_DECLARATION:
                    fn = _parse_method(member, source, parent_type=node.type)
                    if self.include_private or not fn.is_private:
                        cls.methods.append(fn)
                elif member.type == _PROPERTY_DECLARATION:
                    if self.include_private or _is_exported(member, source, parent_type=node.type):
                        cls.class_vars.extend(_parse_property(member, source))
                elif member.type == _CONST_DECLARATION:
                    if self.include_private or _is_exported(member, source, parent_type=node.type):
                        cls.class_vars.extend(_parse_const(member, source))
                elif member.type == _ENUM_CASE:
                    # enums
                    name_node_ec = member.child_by_field_name("name")
                    value_node_ec = member.child_by_field_name("value")
                    cls.class_vars.append(
                        ParsedConstant(
                            name=_text(name_node_ec, source),
                            value=_text(value_node_ec, source),
                        )
                    )

        if self.include_private or is_exported:
            module.classes.append(cls)
