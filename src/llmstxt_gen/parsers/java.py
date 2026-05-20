"""Java parser backed by tree-sitter.

Extracts package Javadoc, public/protected classes, interfaces, enums, records,
and their members. Inner classes are flattened into the module's class list
using dotted names (e.g., ``Outer.Inner``).
"""

from __future__ import annotations

from typing import Any

import tree_sitter_java
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

_JAVA_LANGUAGE = Language(tree_sitter_java.language())

_COMMENT = "comment"
_BLOCK_COMMENT = "block_comment"
_LINE_COMMENT = "line_comment"
_INTERFACE_DECLARATION = "interface_declaration"
_MODIFIERS = "modifiers"
_MARKER_ANNOTATION = "marker_annotation"
_ANNOTATION = "annotation"
_FORMAL_PARAMETER = "formal_parameter"
_SPREAD_PARAMETER = "spread_parameter"
_CONSTRUCTOR_DECLARATION = "constructor_declaration"
_VOID_TYPE = "void_type"
_VARIABLE_DECLARATOR = "variable_declarator"
_PACKAGE_DECLARATION = "package_declaration"
_CLASS_DECLARATION = "class_declaration"
_ENUM_DECLARATION = "enum_declaration"
_RECORD_DECLARATION = "record_declaration"
_ANNOTATION_TYPE_DECLARATION = "annotation_type_declaration"
_METHOD_DECLARATION = "method_declaration"
_FIELD_DECLARATION = "field_declaration"
_ENUM_CONSTANT = "enum_constant"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_javadoc(node: Node, source: bytes) -> str:
    """Extract Javadoc comment immediately preceding the node."""
    prev = node.prev_sibling
    # Tree-sitter-java often puts comments as siblings.
    # We look for block_comment that starts with /**
    while prev and prev.type in (_COMMENT, _BLOCK_COMMENT, _LINE_COMMENT):
        if prev.type == _BLOCK_COMMENT:
            text = _text(prev, source).strip()
            if text.startswith("/**"):
                # It's a Javadoc
                lines = text[3:-2].strip().splitlines()
                processed = []
                for line in lines:
                    line = line.strip().lstrip("*").strip()
                    processed.append(line)
                return "\n".join(processed).strip()
        prev = prev.prev_sibling
    return ""


def _is_exported(node: Node, source: bytes, parent_type: str | None = None) -> bool:
    """Check if a node has public or protected modifiers.

    In interfaces, members are public by default.
    """
    if parent_type == _INTERFACE_DECLARATION:
        return True

    # Find modifiers node. It's usually a named child of the declaration.
    modifiers = None
    for child in node.children:
        if child.type == _MODIFIERS:
            modifiers = child
            break

    if not modifiers:
        return False
    for child in modifiers.children:
        text = _text(child, source)
        if text in ("public", "protected"):
            return True
    return False


def _get_modifiers(node: Node) -> Node | None:
    for child in node.children:
        if child.type == _MODIFIERS:
            return child
    return None


def _get_annotations(node: Node, source: bytes) -> list[str]:
    modifiers = _get_modifiers(node)
    annotations = []
    if modifiers:
        for child in modifiers.children:
            if child.type in (_MARKER_ANNOTATION, _ANNOTATION):
                # For marker_annotation: @Deprecated
                # For annotation: @SuppressWarnings("...")
                annotations.append(_text(child, source))
    return annotations


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if not params_node:
        return []
    params = []
    for child in params_node.named_children:
        if child.type == _FORMAL_PARAMETER:
            type_node = child.child_by_field_name("type")
            name_node = child.child_by_field_name("name")
            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    type_hint=_text(type_node, source) if type_node else "",
                )
            )
        elif child.type == _SPREAD_PARAMETER:
            # type... name
            type_node = child.child_by_field_name("type")
            name_node = child.child_by_field_name("name")
            params.append(
                ParsedParameter(
                    name=f"...{_text(name_node, source)}" if name_node else "...",
                    type_hint=_text(type_node, source) if type_node else "",
                )
            )
    return params


def _parse_method(node: Node, source: bytes, parent_type: str | None = None) -> ParsedFunction:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    type_node = node.child_by_field_name("type")  # return type

    # Generic methods: <T> T method(T t)
    # tree-sitter-java: type_parameters might be present
    type_params = node.child_by_field_name("type_parameters")
    type_params_text = _text(type_params, source) + " " if type_params else ""

    return_type = ""
    if type_node:
        return_type = type_params_text + _text(type_node, source)
    elif node.type == _CONSTRUCTOR_DECLARATION:
        return_type = ""  # Constructors don't have return type in our model
    else:
        # Check for void_type
        for child in node.children:
            if child.type == _VOID_TYPE:
                return_type = type_params_text + "void"
                break

    name = _text(name_node, source) if name_node else ""

    return ParsedFunction(
        name=name,
        parameters=_parse_parameters(params_node, source),
        return_type=return_type,
        docstring=_get_javadoc(node, source),
        line=node.start_point[0] + 1,
        decorators=_get_annotations(node, source),
        is_private=not _is_exported(node, source, parent_type),
    )


def _parse_field(node: Node, source: bytes) -> list[ParsedConstant]:
    # field_declaration can have multiple variables: public int a, b;
    type_node = node.child_by_field_name("type")
    type_hint = _text(type_node, source) if type_node else ""
    constants = []
    for child in node.children:
        # Actually field_declaration children include modifiers, type, and variable_declarator
        if child.type == _VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            constants.append(
                ParsedConstant(
                    name=_text(name_node, source) if name_node else "",
                    type_hint=type_hint,
                    value=_text(value_node, source) if value_node else "",
                )
            )
    return constants


class JavaParser(BaseParser):
    """Parse Java source via tree-sitter."""

    language = "java"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_JAVA_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        # Package docstring
        package_node = None
        for child in root.named_children:
            if child.type == _PACKAGE_DECLARATION:
                package_node = child
                break

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="java",
            docstring=_get_javadoc(package_node, source) if package_node else "",
        )

        for child in root.named_children:
            if child.type in (
                _CLASS_DECLARATION,
                _INTERFACE_DECLARATION,
                _ENUM_DECLARATION,
                _RECORD_DECLARATION,
                _ANNOTATION_TYPE_DECLARATION,
            ):
                self._parse_class_to_module(child, source, module)

        return module

    def _parse_class_to_module(
        self, node: Node, source: bytes, module: ParsedModule, prefix: str = ""
    ) -> None:
        name_node = node.child_by_field_name("name")
        raw_name = _text(name_node, source) if name_node else ""
        name = f"{prefix}{raw_name}" if prefix else raw_name

        is_exported = _is_exported(node, source)

        # Handle record components
        class_vars: list[ParsedConstant] = []
        if node.type == _RECORD_DECLARATION:
            params_node = node.child_by_field_name("parameters")
            if params_node:
                for param in _parse_parameters(params_node, source):
                    class_vars.append(ParsedConstant(name=param.name, type_hint=param.type_hint))

        # Bases
        bases = []
        # superclass
        superclass = node.child_by_field_name("superclass")
        if superclass:
            # superclass node usually contains 'extends' and the type
            for c in superclass.children:
                if c.type not in ("extends",):
                    bases.append(_text(c, source))
        # interfaces
        interfaces = node.child_by_field_name("interfaces")
        if interfaces:
            for c in interfaces.children:
                if c.type not in ("implements", "extends", ","):
                    bases.append(_text(c, source))

        # Generics on class
        type_params = node.child_by_field_name("type_parameters")
        type_params_text = _text(type_params, source) if type_params else ""
        name_with_generics = name + type_params_text

        cls = ParsedClass(
            name=name_with_generics,
            docstring=_get_javadoc(node, source),
            bases=bases,
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == _METHOD_DECLARATION or member.type == _CONSTRUCTOR_DECLARATION:
                    fn = _parse_method(member, source, parent_type=node.type)
                    if self.include_private or not fn.is_private:
                        cls.methods.append(fn)
                elif member.type == _FIELD_DECLARATION:
                    if self.include_private or _is_exported(member, source, parent_type=node.type):
                        cls.class_vars.extend(_parse_field(member, source))
                elif member.type in (
                    _CLASS_DECLARATION,
                    _INTERFACE_DECLARATION,
                    _ENUM_DECLARATION,
                    _RECORD_DECLARATION,
                    _ANNOTATION_TYPE_DECLARATION,
                ):
                    # Recursive for inner classes
                    self._parse_class_to_module(member, source, module, prefix=f"{name}.")
                elif member.type == _ENUM_CONSTANT:
                    # For enums
                    # enum_constant has name field
                    name_node_ec = member.child_by_field_name("name")
                    if name_node_ec:
                        cls.class_vars.append(ParsedConstant(name=_text(name_node_ec, source)))

        if self.include_private or is_exported:
            module.classes.append(cls)
        elif not prefix:
            pass
