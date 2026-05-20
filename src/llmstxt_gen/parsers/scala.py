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


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_docstring(node: Node, source: bytes) -> str:
    """Extract ScalaDoc comment immediately preceding the node."""
    prev = node.prev_sibling
    # In Scala, comments are often siblings.
    # Look for block_comment that starts with /**
    while prev and prev.type in ("comment", "block_comment", "line_comment"):
        if prev.type == "block_comment":
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
        if child.type == "modifiers":
            modifiers = child
            break

    if not modifiers:
        return False

    return any(child.type == "access_modifier" for child in modifiers.children)


def _get_child_by_type(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _get_type_after_colon(node: Node) -> Node | None:
    for i, child in enumerate(node.children):
        if child.type == ":" and i + 1 < len(node.children):
            return node.children[i + 1]
    return None


def _get_value_after_equals(node: Node) -> Node | None:
    for i, child in enumerate(node.children):
        if child.type == "=" and i + 1 < len(node.children):
            return node.children[i + 1]
    return None


def _find_all_identifiers(node: Node) -> list[Node]:
    """Recursively find all identifiers within a node (e.g. for tuple patterns)."""
    if node.type == "identifier":
        return [node]
    ids = []
    for child in node.children:
        if child.type in ("template_body", "template_definition", "function_definition"):
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
        if child.type in ("implicit", "using"):
            prefix = f"{child.type} "
        elif child.type in ("parameter", "class_parameter"):
            name_node = _get_child_by_type(child, "identifier")
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
        if child.type == "parameters":
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
        if child.type in ("identifiers", "tuple_pattern", "identifier", "variable_pattern"):
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
                "class_definition",
                "object_definition",
                "trait_definition",
                "enum_definition",
            ):
                self._parse_class_like(child, source, classes_by_name)
            elif child.type in ("function_definition", "function_declaration"):
                fn = _parse_function(child, source)
                if self.include_private or not fn.is_private:
                    module.functions.append(fn)
            elif child.type in ("val_definition", "var_definition", "val_declaration", "var_declaration"):
                if self.include_private or not _is_private(child):
                    module.constants.extend(_parse_val_var(child, source))
            elif child.type == "extension_definition":
                self._parse_extension(child, source, module)
            elif child.type == "given_definition":
                self._parse_given(child, source, module)
            elif child.type == "package_clause":
                self._collect_definitions(child, source, module, classes_by_name)

    def _parse_class_like(
        self, node: Node, source: bytes, classes_by_name: dict[str, ParsedClass]
    ) -> None:
        name_node = _get_child_by_type(node, "identifier")
        name = _text(name_node, source) if name_node else ""
        if not name:
            return

        is_private = _is_private(node)
        if not self.include_private and is_private:
            return

        is_object = node.type == "object_definition"

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
                extends_clause = _get_child_by_type(node, "extends_clause")
                if extends_clause:
                    bases = []
                    for c in extends_clause.children:
                        if c.type in ("type_identifier", "generic_type", "user_type"):
                            bases.append(_text(c, source))
                    cls.bases = bases
                cls.line = node.start_point[0] + 1
        else:
            # Type parameters
            type_params_node = _get_child_by_type(node, "type_parameters")
            type_params = _text(type_params_node, source) if type_params_node else ""

            # Bases
            bases = []
            extends_clause = _get_child_by_type(node, "extends_clause")
            if extends_clause:
                for c in extends_clause.children:
                    if c.type in ("type_identifier", "generic_type", "user_type"):
                        bases.append(_text(c, source))

            cls = ParsedClass(
                name=f"{name}{type_params}",
                docstring=_get_docstring(node, source),
                bases=bases,
                line=node.start_point[0] + 1,
            )
            classes_by_name[name] = cls

        # Process body
        template_body = _get_child_by_type(node, "template_body")
        if not template_body:
            # Scala 3 might use indentation instead of braces, or it's an enum body
            template_body = _get_child_by_type(node, "enum_body")

        if template_body:
            for member in template_body.children:
                if member.type in ("function_definition", "function_declaration"):
                    fn = _parse_function(member, source)
                    if self.include_private or not fn.is_private:
                        cls.methods.append(fn)
                elif member.type in ("val_definition", "var_definition", "val_declaration", "var_declaration"):
                    if self.include_private or not _is_private(member):
                        cls.class_vars.extend(_parse_val_var(member, source))
                elif member.type == "enum_case_definitions":
                    for case in member.children:
                        if case.type == "simple_enum_case":
                            case_name_node = _get_child_by_type(case, "identifier")
                            if case_name_node:
                                cls.class_vars.append(
                                    ParsedConstant(name=_text(case_name_node, source))
                                )

        # Class parameters
        class_params_node = _get_child_by_type(node, "class_parameters")
        if class_params_node:
            for child in class_params_node.children:
                if child.type == "class_parameter":
                    is_val_var = False
                    for grandchild in child.children:
                        if grandchild.type in ("val", "var"):
                            is_val_var = True
                            break

                    is_case = any(c.type == "case" for c in node.children)

                    if is_case or is_val_var:
                        p_name_node = _get_child_by_type(child, "identifier")
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
        params_node = _get_child_by_type(node, "parameters")
        recv_text = ""
        if params_node:
            params = _parse_parameters(params_node, source)
            if params:
                p = params[0]
                recv_text = f"{p.name}: {p.type_hint}"

        for child in node.children:
            if child.type == "function_definition":
                fn = _parse_function(child, source)
                if self.include_private or not fn.is_private:
                    fn.name = f"extension ({recv_text}) {fn.name}"
                    module.functions.append(fn)

    def _parse_given(self, node: Node, source: bytes, module: ParsedModule) -> None:
        name_node = _get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = _text(name_node, source)
        type_node = _get_type_after_colon(node)
        if not type_node:
            for c in node.children:
                if c.type in ("generic_type", "type_identifier"):
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
