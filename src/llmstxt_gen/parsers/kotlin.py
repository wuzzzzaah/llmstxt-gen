"""Kotlin parser backed by tree-sitter.

Extracts KDoc comments, top-level functions, classes, interfaces, objects,
and their members. Respects the include_private flag.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_kotlin
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

_KT_LANGUAGE = Language(tree_sitter_kotlin.language())


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_kdoc(node: Node, source: bytes) -> str:
    """Extract KDoc comment immediately preceding the node."""
    prev = node.prev_sibling
    # If the node is preceded by an annotated_expression, the KDoc might be before THAT.
    while prev and prev.type in (
        "comment",
        "block_comment",
        "line_comment",
        "annotated_expression",
    ):
        if prev.type == "block_comment":
            text = _text(prev, source).strip()
            if text.startswith("/**"):
                # It's a KDoc
                lines = text[3:-2].strip().splitlines()
                processed = []
                for line in lines:
                    line = line.strip().lstrip("*").strip()
                    processed.append(line)
                return "\n".join(processed).strip()
        if prev.type == "annotated_expression":
            # Continue searching before the annotation
            prev = prev.prev_sibling
            continue
        prev = prev.prev_sibling
    return ""


def _is_private(node: Node, source: bytes) -> bool:
    """Check if a node has private or internal modifiers."""
    modifiers = None
    for child in node.children:
        if child.type == "modifiers":
            modifiers = child
            break

    if not modifiers:
        return False

    for child in modifiers.children:
        if child.type == "visibility_modifier":
            for c in child.children:
                if c.type in ("private", "internal"):
                    return True
            text = _text(child, source)
            if text in ("private", "internal"):
                return True
        elif child.type in ("private", "internal"):
            return True
    return False


def _get_annotations(node: Node, source: bytes) -> list[str]:
    # 1. Check modifiers
    modifiers = None
    for child in node.children:
        if child.type == "modifiers":
            modifiers = child
            break

    annotations = []
    if modifiers:
        for child in modifiers.children:
            if child.type == "annotation":
                annotations.append(_text(child, source))

    # 2. Check preceding annotated_expression siblings (top-level or in bodies)
    prev = node.prev_sibling
    while prev and prev.type == "annotated_expression":
        for child in prev.children:
            if child.type == "annotation":
                annotations.append(
                    _text(prev, source)
                )  # Capture the full annotated_expression text
                break
        prev = prev.prev_sibling

    return annotations


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if not params_node:
        return []
    params = []
    # function_value_parameters or class_parameters
    # We need to handle both the child nodes and their potentially succeeding '=' siblings
    children = params_node.children
    for i, child in enumerate(children):
        if child.type in ("parameter", "class_parameter"):
            name_node = None
            type_node = None

            for c in child.children:
                if c.type == "identifier":
                    name_node = c
                elif c.type in ("user_type", "nullable_type", "function_type"):
                    type_node = c

            default_node = None
            if i + 1 < len(children) and children[i + 1].type == "=" and i + 2 < len(children):
                default_node = children[i + 2]

            if not default_node:
                found_eq = False
                for c in child.children:
                    if c.type == "=":
                        found_eq = True
                    elif found_eq:
                        default_node = c
                        break

            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    type_hint=_text(type_node, source) if type_node else "",
                    default=_text(default_node, source) if default_node else "",
                )
            )
    return params


def _parse_function(node: Node, source: bytes) -> ParsedFunction:
    name_node = None
    for c in node.children:
        if c.type == "identifier":
            name_node = c
            break

    params_node = None
    for c in node.children:
        if c.type == "function_value_parameters":
            params_node = c
            break

    return_type = ""
    found_params = False
    for child in node.children:
        if child.type == "function_value_parameters":
            found_params = True
        elif found_params and child.type == ":":
            continue
        elif found_params and child.type in ("user_type", "nullable_type", "function_type"):
            return_type = _text(child, source)
            break
        elif found_params and child.type == "function_body":
            break

    receiver_type = ""
    for child in node.children:
        if child == name_node:
            break
        if child.type in ("user_type", "nullable_type", "function_type"):
            receiver_type = _text(child, source) + "."
            break

    name = _text(name_node, source) if name_node else ""
    full_name = f"{receiver_type}{name}"

    return ParsedFunction(
        name=full_name,
        parameters=_parse_parameters(params_node, source),
        return_type=return_type,
        docstring=_get_kdoc(node, source),
        line=node.start_point[0] + 1,
        decorators=_get_annotations(node, source),
        is_private=_is_private(node, source),
    )


def _parse_property(node: Node, source: bytes) -> ParsedConstant:
    var_decl = None
    for c in node.children:
        if c.type == "variable_declaration":
            var_decl = c
            break

    name = ""
    type_hint = ""
    if var_decl:
        id_node = None
        type_node = None
        for c in var_decl.children:
            if c.type == "identifier":
                id_node = c
            elif c.type in ("user_type", "nullable_type", "function_type"):
                type_node = c

        name = _text(id_node, source) if id_node else ""
        type_hint = _text(type_node, source) if type_node else ""

    value = ""
    found_eq = False
    for child in node.children:
        if child.type == "=":
            found_eq = True
        elif found_eq:
            value = _text(child, source)
            break

    return ParsedConstant(
        name=name,
        type_hint=type_hint,
        value=value,
    )


class KotlinParser(BaseParser):
    """Parse Kotlin source via tree-sitter."""

    language = "kotlin"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_KT_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        package_node = None
        for child in root.named_children:
            if child.type == "package_header":
                package_node = child
                break

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="kotlin",
            docstring=_get_kdoc(package_node, source) if package_node else "",
        )

        if not module.docstring:
            first_child = root.named_children[0] if root.named_children else None
            if first_child:
                module.docstring = _get_kdoc(first_child, source)

        for child in root.named_children:
            if child.type == "import_header":
                # kotlin: (import_header (identifier) [(import_alias)] [(asterisk)])
                # or (import_header (user_type))
                for named_child in child.named_children:
                    if named_child.type not in ("import", "import_alias", "*"):
                        module.imports.append(_text(named_child, source))
                continue

            if child.type == "function_declaration":
                fn = _parse_function(child, source)
                if self.include_private or not fn.is_private:
                    module.functions.append(fn)
            elif child.type in ("class_declaration", "object_declaration"):
                self._parse_class_to_module(child, source, module)
            elif child.type == "property_declaration":
                if self.include_private or not _is_private(child, source):
                    module.constants.append(_parse_property(child, source))

        return module

    def _parse_class_to_module(
        self, node: Node, source: bytes, module: ParsedModule, prefix: str = ""
    ) -> None:
        name_node = None
        for c in node.children:
            if c.type == "identifier":
                name_node = c
                break
        raw_name = _text(name_node, source) if name_node else ""
        name = f"{prefix}{raw_name}" if prefix else raw_name

        bases = []
        delegation_specifiers = None
        for c in node.children:
            if c.type == "delegation_specifiers":
                delegation_specifiers = c
                break

        if delegation_specifiers:
            for spec in delegation_specifiers.children:
                if spec.type == "delegation_specifier":
                    for inner in spec.children:
                        if inner.type == "constructor_invocation":
                            user_type_node = None
                            for c in inner.children:
                                if c.type == "user_type":
                                    user_type_node = c
                                    break
                            if user_type_node:
                                bases.append(_text(user_type_node, source))
                        elif inner.type == "user_type":
                            bases.append(_text(inner, source))

        type_params = None
        for c in node.children:
            if c.type == "type_parameters":
                type_params = c
                break
        type_params_text = _text(type_params, source) if type_params else ""

        class_vars: list[ParsedConstant] = []
        primary_ctor = None
        for c in node.children:
            if c.type == "primary_constructor":
                primary_ctor = c
                break

        if primary_ctor:
            class_params = None
            for c in primary_ctor.children:
                if c.type == "class_parameters":
                    class_params = c
                    break
            if class_params:
                for child in class_params.named_children:
                    if child.type == "class_parameter":
                        has_val_or_var = any(c.type in ("val", "var") for c in child.children)
                        if has_val_or_var:
                            param_id_node = None
                            param_type_node = None
                            for c in child.children:
                                if c.type == "identifier":
                                    param_id_node = c
                                elif c.type in ("user_type", "nullable_type", "function_type"):
                                    param_type_node = c

                            if self.include_private or not _is_private(child, source):
                                class_vars.append(
                                    ParsedConstant(
                                        name=_text(param_id_node, source) if param_id_node else "",
                                        type_hint=_text(param_type_node, source)
                                        if param_type_node
                                        else "",
                                    )
                                )

        cls = ParsedClass(
            name=name + type_params_text,
            docstring=_get_kdoc(node, source),
            bases=bases,
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )

        body = None
        for c in node.children:
            if c.type in ("class_body", "enum_class_body"):
                body = c
                break

        if body:
            for member in body.named_children:
                if member.type == "function_declaration":
                    fn = _parse_function(member, source)
                    if self.include_private or not fn.is_private:
                        cls.methods.append(fn)
                elif member.type == "property_declaration":
                    if self.include_private or not _is_private(member, source):
                        prop = _parse_property(member, source)
                        cls.class_vars.append(prop)
                elif member.type in ("class_declaration", "object_declaration"):
                    # Inner classes / Nested objects
                    self._parse_class_to_module(member, source, module, prefix=f"{name}.")
                elif member.type == "companion_object":
                    companion_body = None
                    for c in member.children:
                        if c.type == "class_body":
                            companion_body = c
                            break
                    if companion_body:
                        for c_member in companion_body.named_children:
                            if c_member.type == "function_declaration":
                                fn = _parse_function(c_member, source)
                                if self.include_private or not fn.is_private:
                                    cls.methods.append(fn)
                            elif c_member.type == "property_declaration":
                                if self.include_private or not _is_private(c_member, source):
                                    cls.class_vars.append(_parse_property(c_member, source))
                elif member.type == "enum_entry":
                    id_node = None
                    for c in member.children:
                        if c.type == "identifier":
                            id_node = c
                            break
                    if id_node:
                        cls.class_vars.append(ParsedConstant(name=_text(id_node, source)))

        if self.include_private or not _is_private(node, source):
            module.classes.append(cls)
