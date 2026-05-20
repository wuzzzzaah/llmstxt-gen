"""Scala parser backed by tree-sitter.

Extracts ScalaDoc, classes, objects, traits, enums, methods, and members.
Handles Scala 3 features like given instances and extension methods.
Companion objects are merged into their associated classes.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_scala
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

_SCALA_LANGUAGE = Language(tree_sitter_scala.language())

_COMMENT = "comment"
_BLOCK_COMMENT = "block_comment"
_LINE_COMMENT = "line_comment"
_MODIFIERS = "modifiers"
_ACCESS_MODIFIER = "access_modifier"
_COLON = ":"
_EQUAL = "="
_IDENTIFIER = "identifier"
_TEMPLATE_BODY = "template_body"
_TEMPLATE_DEFINITION = "template_definition"
_FUNCTION_DEFINITION = "function_definition"
_IMPLICIT = "implicit"
_USING = "using"
_PARAMETER = "parameter"
_CLASS_PARAMETER = "class_parameter"
_PARAMETERS = "parameters"
_IDENTIFIERS = "identifiers"
_TUPLE_PATTERN = "tuple_pattern"
_VARIABLE_PATTERN = "variable_pattern"
_CLASS_DEFINITION = "class_definition"
_OBJECT_DEFINITION = "object_definition"
_TRAIT_DEFINITION = "trait_definition"
_ENUM_DEFINITION = "enum_definition"
_FUNCTION_DECLARATION = "function_declaration"
_VAL_DEFINITION = "val_definition"
_VAR_DEFINITION = "var_definition"
_VAL_DECLARATION = "val_declaration"
_VAR_DECLARATION = "var_declaration"
_EXTENSION_DEFINITION = "extension_definition"
_GIVEN_DEFINITION = "given_definition"
_PACKAGE_CLAUSE = "package_clause"
_TYPE_IDENTIFIER = "type_identifier"
_GENERIC_TYPE = "generic_type"
_USER_TYPE = "user_type"
_EXTENDS_CLAUSE = "extends_clause"
_ENUM_BODY = "enum_body"
_ENUM_CASE_DEFINITIONS = "enum_case_definitions"
_SIMPLE_ENUM_CASE = "simple_enum_case"
_VAL = "val"
_VAR = "var"
_CASE = "case"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_docstring(node: Node, source: bytes) -> str:
    """Extract ScalaDoc comment immediately preceding the node."""
    prev = node.prev_sibling
    # In Scala, comments are often siblings.
    # Look for block_comment that starts with /**
    while prev and prev.type in (_COMMENT, _BLOCK_COMMENT, _LINE_COMMENT):
        if prev.type == _BLOCK_COMMENT:
            text = _text(prev, source).strip()
            if text.startswith("/**"):
                lines = text[3:-2].strip().splitlines()
                processed = []
                for line in lines:
                    line = line.strip().lstrip("*").strip()
                    processed.append(line)
                return "\n".join(processed).strip()
        prev = prev.prev_sibling
    return ""


def _is_private(node: Node) -> bool:
    """Check if a node has private or protected modifiers.

    In Scala, private and protected (including qualified versions like private[pkg])
    are considered non-public for our purposes.
    """
    modifiers = None
    for child in node.children:
        if child.type == _MODIFIERS:
            modifiers = child
            break

    if not modifiers:
        return False

    return any(child.type == _ACCESS_MODIFIER for child in modifiers.children)


def _get_child_by_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _get_type_after_colon(node: Node) -> Node | None:
    for i, child in enumerate(node.children):
        if child.type == _COLON and i + 1 < len(node.children):
            return node.children[i + 1]
    return None


def _get_value_after_equals(node: Node) -> Node | None:
    for i, child in enumerate(node.children):
        if child.type == _EQUAL and i + 1 < len(node.children):
            return node.children[i + 1]
    return None


def _find_all_identifiers(node: Node) -> list[Node]:
    """Recursively find all identifiers within a node (e.g. for tuple patterns)."""
    if node.type == _IDENTIFIER:
        return [node]
    ids = []
    for child in node.children:
        if child.type in (_TEMPLATE_BODY, _TEMPLATE_DEFINITION, _FUNCTION_DEFINITION):
            # Do not recurse into nested definitions
            continue
        ids.extend(_find_all_identifiers(child))
    return ids


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if not params_node:
        return []
    params = []

    prefix = ""
    # Check for implicit or using keywords in the parameters list
    for child in params_node.children:
        if child.type in (_IMPLICIT, _USING):
            prefix = f"{child.type} "
        elif child.type in (_PARAMETER, _CLASS_PARAMETER):
            name_node = _get_child_by_type(child, _IDENTIFIER)
            type_node = _get_type_after_colon(child)
            default_node = _get_value_after_equals(child)

            name = _text(name_node, source) if name_node else ""
            if name and prefix:
                name = prefix + name

            params.append(
                ParsedParameter(
                    name=name,
                    type_hint=_text(type_node, source) if type_node else "",
                    default=_text(default_node, source) if default_node else "",
                )
            )
    return params


def _parse_function(node: Node, source: bytes) -> ParsedFunction:
    name_node = _get_child_by_type(node, "identifier")
    name = _text(name_node, source) if name_node else ""

    # Scala functions can have multiple parameter lists
    all_params = []
    for child in node.children:
        if child.type == _PARAMETERS:
            all_params.extend(_parse_parameters(child, source))

    type_node = _get_type_after_colon(node)

    return ParsedFunction(
        name=name,
        parameters=all_params,
        return_type=_text(type_node, source) if type_node else "",
        docstring=_get_docstring(node, source),
        line=node.start_point[0] + 1,
        is_private=_is_private(node),
    )


def _parse_val_var(node: Node, source: bytes) -> list[ParsedConstant]:
    # val x, y: Int = 1
    # val (a, b) = (2, 3)
    type_node = _get_type_after_colon(node)
    type_hint = _text(type_node, source) if type_node else ""
    value_node = _get_value_after_equals(node)
    value = _text(value_node, source) if value_node else ""

    constants = []
    # In Scala tree-sitter, identifiers can be nested (identifiers node, tuple_pattern, etc)
    # We want to find all identifier nodes that are before the colon or equals sign.

    # Simple heuristic: find all identifier nodes that are children or grandchildren of patterns
    for child in node.children:
        if child.type in (_IDENTIFIERS, _TUPLE_PATTERN, _IDENTIFIER, _VARIABLE_PATTERN):
            for id_node in _find_all_identifiers(child):
                constants.append(
                    ParsedConstant(
                        name=_text(id_node, source),
                        type_hint=type_hint,
                        value=value,
                    )
                )
    return constants


class ScalaParser(BaseParser):
    """Parse Scala source via tree-sitter."""

    language = "scala"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_SCALA_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="scala",
        )

        # First pass: collect all classes and objects
        classes_by_name: dict[str, ParsedClass] = {}

        self._collect_definitions(root, source, module, classes_by_name)

        # Add collected classes to module
        for cls in classes_by_name.values():
            module.classes.append(cls)

        return module

    def _collect_definitions(
        self,
        node: Node,
        source: bytes,
        module: ParsedModule,
        classes_by_name: dict[str, ParsedClass],
    ) -> None:
        for child in node.children:
            if child.type in (
                _CLASS_DEFINITION,
                _OBJECT_DEFINITION,
                _TRAIT_DEFINITION,
                _ENUM_DEFINITION,
            ):
                self._parse_class_like(child, source, classes_by_name)
            elif child.type in (_FUNCTION_DEFINITION, _FUNCTION_DECLARATION):
                fn = _parse_function(child, source)
                if self.include_private or not fn.is_private:
                    module.functions.append(fn)
            elif child.type in (
                _VAL_DEFINITION,
                _VAR_DEFINITION,
                _VAL_DECLARATION,
                _VAR_DECLARATION,
            ):
                if self.include_private or not _is_private(child):
                    module.constants.extend(_parse_val_var(child, source))
            elif child.type == _EXTENSION_DEFINITION:
                self._parse_extension(child, source, module)
            elif child.type == _GIVEN_DEFINITION:
                self._parse_given(child, source, module)
            elif child.type == _PACKAGE_CLAUSE:
                self._collect_definitions(child, source, module, classes_by_name)

    def _parse_class_like(
        self, node: Node, source: bytes, classes_by_name: dict[str, ParsedClass]
    ) -> None:
        name_node = _get_child_by_type(node, _IDENTIFIER)
        name = _text(name_node, source) if name_node else ""
        if not name:
            return

        is_private = _is_private(node)
        if not self.include_private and is_private:
            return

        is_object = node.type == _OBJECT_DEFINITION

        if name in classes_by_name:
            cls = classes_by_name[name]
            # If we were previously an object and now we are a class/trait/enum,
            # update the ParsedClass with class-specific info while keeping members.
            if not is_object:
                # Update docstring, bases, line if they are not set or if class should take precedence
                if not cls.docstring:
                    cls.docstring = _get_docstring(node, source)

                # Type parameters
                type_params_node = _get_child_by_type(node, "type_parameters")
                type_params = _text(type_params_node, source) if type_params_node else ""
                cls.name = f"{name}{type_params}"

                # Bases
                extends_clause = _get_child_by_type(node, _EXTENDS_CLAUSE)
                if extends_clause:
                    bases = []
                    for c in extends_clause.children:
                        if c.type in (_TYPE_IDENTIFIER, _GENERIC_TYPE, _USER_TYPE):
                            bases.append(_text(c, source))
                    cls.bases = bases
                cls.line = node.start_point[0] + 1
        else:
            # Type parameters
            type_params_node = _get_child_by_type(node, "type_parameters")
            type_params = _text(type_params_node, source) if type_params_node else ""

            # Bases
            bases = []
            extends_clause = _get_child_by_type(node, _EXTENDS_CLAUSE)
            if extends_clause:
                for c in extends_clause.children:
                    if c.type in (_TYPE_IDENTIFIER, _GENERIC_TYPE, _USER_TYPE):
                        bases.append(_text(c, source))

            cls = ParsedClass(
                name=f"{name}{type_params}",
                docstring=_get_docstring(node, source),
                bases=bases,
                line=node.start_point[0] + 1,
            )
            classes_by_name[name] = cls

        # Process body
        template_body = _get_child_by_type(node, _TEMPLATE_BODY)
        if not template_body:
            # Scala 3 might use indentation instead of braces, or it's an enum body
            template_body = _get_child_by_type(node, _ENUM_BODY)

        if template_body:
            for member in template_body.children:
                if member.type in (_FUNCTION_DEFINITION, _FUNCTION_DECLARATION):
                    fn = _parse_function(member, source)
                    if self.include_private or not fn.is_private:
                        cls.methods.append(fn)
                elif member.type in (
                    _VAL_DEFINITION,
                    _VAR_DEFINITION,
                    _VAL_DECLARATION,
                    _VAR_DECLARATION,
                ):
                    if self.include_private or not _is_private(member):
                        cls.class_vars.extend(_parse_val_var(member, source))
                elif member.type == _ENUM_CASE_DEFINITIONS:
                    for case in member.children:
                        if case.type == _SIMPLE_ENUM_CASE:
                            case_name_node = _get_child_by_type(case, _IDENTIFIER)
                            if case_name_node:
                                cls.class_vars.append(
                                    ParsedConstant(name=_text(case_name_node, source))
                                )

        # Class parameters
        class_params_node = _get_child_by_type(node, "class_parameters")
        if class_params_node:
            for child in class_params_node.children:
                if child.type == _CLASS_PARAMETER:
                    is_val_var = False
                    for grandchild in child.children:
                        if grandchild.type in (_VAL, _VAR):
                            is_val_var = True
                            break

                    is_case = any(c.type == _CASE for c in node.children)

                    if is_case or is_val_var:
                        p_name_node = _get_child_by_type(child, _IDENTIFIER)
                        p_type_node = _get_type_after_colon(child)
                        p_value_node = _get_value_after_equals(child)
                        if p_name_node:
                            cls.class_vars.append(
                                ParsedConstant(
                                    name=_text(p_name_node, source),
                                    type_hint=_text(p_type_node, source) if p_type_node else "",
                                    value=_text(p_value_node, source) if p_value_node else "",
                                )
                            )

    def _parse_extension(self, node: Node, source: bytes, module: ParsedModule) -> None:
        params_node = _get_child_by_type(node, _PARAMETERS)
        recv_text = ""
        if params_node:
            params = _parse_parameters(params_node, source)
            if params:
                p = params[0]
                recv_text = f"{p.name}: {p.type_hint}"

        for child in node.children:
            if child.type == _FUNCTION_DEFINITION:
                fn = _parse_function(child, source)
                if self.include_private or not fn.is_private:
                    fn.name = f"extension ({recv_text}) {fn.name}"
                    module.functions.append(fn)

    def _parse_given(self, node: Node, source: bytes, module: ParsedModule) -> None:
        name_node = _get_child_by_type(node, _IDENTIFIER)
        if not name_node:
            return

        name = _text(name_node, source)
        type_node = _get_type_after_colon(node)
        if not type_node:
            for c in node.children:
                if c.type in (_GENERIC_TYPE, _TYPE_IDENTIFIER):
                    type_node = c
                    break

        return_type = _text(type_node, source) if type_node else ""

        fn = ParsedFunction(
            name=f"given {name}",
            parameters=[],
            return_type=return_type,
            docstring=_get_docstring(node, source),
            line=node.start_point[0] + 1,
            is_private=_is_private(node),
        )
        if self.include_private or not fn.is_private:
            module.functions.append(fn)
