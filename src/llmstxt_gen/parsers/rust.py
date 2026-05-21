"""Rust parser backed by tree-sitter.

Extracts module doc comments, public functions, structs, enums, traits,
impl blocks, and constants. Non-public items are omitted unless the
caller opts in via :class:`RustParser` ``include_private``.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_rust
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

_RUST_LANGUAGE = Language(tree_sitter_rust.language())

_VISIBILITY_MODIFIER = "visibility_modifier"
_LINE_COMMENT = "line_comment"
_SOURCE_FILE = "source_file"
_ATTRIBUTE_ITEM = "attribute_item"
_INNER_ATTRIBUTE_ITEM = "inner_attribute_item"
_PARAMETER = "parameter"
_SELF_PARAMETER = "self_parameter"
_FUNCTION_ITEM = "function_item"
_STRUCT_ITEM = "struct_item"
_ENUM_ITEM = "enum_item"
_TRAIT_ITEM = "trait_item"
_TYPE_ITEM = "type_item"
_CONST_ITEM = "const_item"
_STATIC_ITEM = "static_item"
_IMPL_ITEM = "impl_item"
_WHERE_CLAUSE = "where_clause"
_FIELD_DECLARATION_LIST = "field_declaration_list"
_FIELD_DECLARATION = "field_declaration"
_ENUM_VARIANT = "enum_variant"
_FUNCTION_SIGNATURE_ITEM = "function_signature_item"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _is_public(node: Node) -> bool:
    """Check if a node has a visibility modifier (pub, pub(crate), etc.)."""
    return any(child.type == _VISIBILITY_MODIFIER for child in node.children)


def _get_doc(node: Node, source: bytes) -> str:
    """Extract doc comments (/// or //!) above or inside a node."""
    docs: list[str] = []

    # Outer doc comments (///) are usually preceding siblings
    prev = node.prev_sibling
    while prev and prev.type == _LINE_COMMENT:
        text = _text(prev, source).strip()
        if text.startswith("///"):
            docs.insert(0, text[3:].strip())
        prev = prev.prev_sibling

    # Inner doc comments (//!) might be inside the node (e.g. at the start of a module or function body)
    # But for module level, they are just top-level nodes.
    if node.type == _SOURCE_FILE:
        for child in node.children:
            if child.type == _LINE_COMMENT:
                text = _text(child, source).strip()
                if text.startswith("//!"):
                    docs.append(text[3:].strip())
            elif child.type not in (_LINE_COMMENT, _ATTRIBUTE_ITEM, _INNER_ATTRIBUTE_ITEM):
                # Stop at the first non-comment/attribute item for module docs
                break

    return "\n".join(docs).strip()


def _parse_parameters(node: Node, source: bytes) -> list[ParsedParameter]:
    params_node = node.child_by_field_name("parameters")
    if not params_node:
        return []

    params: list[ParsedParameter] = []
    for child in params_node.named_children:
        if child.type == _PARAMETER:
            pattern = child.child_by_field_name("pattern")
            type_node = child.child_by_field_name("type")
            params.append(
                ParsedParameter(
                    name=_text(pattern, source) if pattern else "",
                    type_hint=_text(type_node, source) if type_node else "",
                )
            )
        elif child.type == _SELF_PARAMETER:
            params.append(ParsedParameter(name=_text(child, source)))
    return params


class RustParser(BaseParser):
    """Parse Rust source via tree-sitter."""

    language = "rust"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_RUST_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="rust",
            docstring=_get_doc(root, source),
        )

        classes_by_name: dict[str, ParsedClass] = {}

        for child in root.named_children:
            if child.type == _FUNCTION_ITEM:
                fn = self._parse_function(child, source)
                if self.include_private or _is_public(child):
                    module.functions.append(fn)

            elif child.type == _STRUCT_ITEM:
                cls = self._parse_struct(child, source)
                if self.include_private or _is_public(child):
                    classes_by_name[cls.name] = cls
                    module.classes.append(cls)

            elif child.type == _ENUM_ITEM:
                cls = self._parse_enum(child, source)
                if self.include_private or _is_public(child):
                    classes_by_name[cls.name] = cls
                    module.classes.append(cls)

            elif child.type == _TRAIT_ITEM:
                cls = self._parse_trait(child, source)
                if self.include_private or _is_public(child):
                    classes_by_name[cls.name] = cls
                    module.classes.append(cls)

            elif child.type == _TYPE_ITEM:
                if self.include_private or _is_public(child):
                    # Map type aliases to a simple class or just a constant?
                    # Roadmap says "Public type aliases".
                    # Let's map them to ParsedConstant for now as they are simple name = type.
                    name_node = child.child_by_field_name("name")
                    type_node = child.child_by_field_name("type")
                    module.constants.append(
                        ParsedConstant(
                            name=_text(name_node, source) if name_node else "",
                            type_hint=_text(type_node, source) if type_node else "",
                        )
                    )

            elif child.type in (_CONST_ITEM, _STATIC_ITEM):
                if self.include_private or _is_public(child):
                    name_node = child.child_by_field_name("name")
                    type_node = child.child_by_field_name("type")
                    val_node = child.child_by_field_name("value")
                    module.constants.append(
                        ParsedConstant(
                            name=_text(name_node, source) if name_node else "",
                            type_hint=_text(type_node, source) if type_node else "",
                            value=_text(val_node, source) if val_node else "",
                        )
                    )

            elif child.type == _IMPL_ITEM:
                self._handle_impl(child, source, classes_by_name, module)

        return module

    def _parse_function(self, node: Node, source: bytes) -> ParsedFunction:
        name_node = node.child_by_field_name("name")
        ret_node = node.child_by_field_name("return_type")

        # Generics and where clause
        generics = ""
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            generics += _text(type_params, source)

        where = ""
        for c in node.children:
            if c.type == _WHERE_CLAUSE:
                where = " " + _text(c, source)
                break

        name = _text(name_node, source) if name_node else ""
        return_type = _text(ret_node, source) if ret_node else ""

        return ParsedFunction(
            name=name + generics + where,
            parameters=_parse_parameters(node, source),
            return_type=return_type,
            docstring=_get_doc(node, source),
            line=node.start_point[0] + 1,
            is_private=not _is_public(node),
        )

    def _parse_struct(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        class_vars: list[ParsedConstant] = []
        body = node.child_by_field_name("body")
        if body and body.type == _FIELD_DECLARATION_LIST:
            for field in body.named_children:
                if field.type == _FIELD_DECLARATION and (
                    self.include_private or _is_public(field)
                ):
                    f_name = field.child_by_field_name("name")
                    f_type = field.child_by_field_name("type")
                    class_vars.append(
                        ParsedConstant(
                            name=_text(f_name, source) if f_name else "",
                            type_hint=_text(f_type, source) if f_type else "",
                        )
                    )

        return ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )

    def _parse_enum(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        variants: list[ParsedConstant] = []
        body = node.child_by_field_name("body")
        if body:
            for variant in body.named_children:
                if variant.type == _ENUM_VARIANT:
                    # For enums, variants are typically public if the enum is.
                    v_name = variant.child_by_field_name("name")
                    # Could have tuple/struct variants, but ParsedConstant is limited.
                    # Roadmap says "variants" map to class_vars.
                    variants.append(
                        ParsedConstant(
                            name=_text(v_name, source) if v_name else "",
                        )
                    )

        return ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            class_vars=variants,
            line=node.start_point[0] + 1,
        )

    def _parse_trait(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        # Generics and where clause
        generics = ""
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            generics += _text(type_params, source)

        where = ""
        for c in node.children:
            if c.type == _WHERE_CLAUSE:
                where = " " + _text(c, source)
                break

        methods: list[ParsedFunction] = []
        body = node.child_by_field_name("body")
        if body:
            for item in body.named_children:
                if item.type in (_FUNCTION_ITEM, _FUNCTION_SIGNATURE_ITEM):
                    # All trait methods are effectively public for users of the trait
                    methods.append(self._parse_function(item, source))

        return ParsedClass(
            name=name + generics + where,
            docstring=_get_doc(node, source),
            methods=methods,
            line=node.start_point[0] + 1,
        )

    def _handle_impl(
        self, node: Node, source: bytes, classes: dict[str, ParsedClass], module: ParsedModule
    ) -> None:
        # impl [Trait for] Type { ... }
        type_node = node.child_by_field_name("type")
        trait_node = node.child_by_field_name("trait")

        if not type_node:
            return

        type_name = _text(type_node, source)

        # If the class isn't in this file, we might need to create it.
        if type_name not in classes:
            new_cls = ParsedClass(name=type_name)
            classes[type_name] = new_cls
            module.classes.append(new_cls)

        cls = classes[type_name]

        body = node.child_by_field_name("body")
        if body:
            for item in body.named_children:
                if item.type == _FUNCTION_ITEM:
                    fn = self._parse_function(item, source)
                    # If it's a trait impl, methods are public.
                    # If it's a regular impl, check visibility.
                    if trait_node or self.include_private or _is_public(item):
                        cls.methods.append(fn)
                elif item.type in (_CONST_ITEM, _STATIC_ITEM):
                    if trait_node or self.include_private or _is_public(item):
                        name_n = item.child_by_field_name("name")
                        type_n = item.child_by_field_name("type")
                        cls.class_vars.append(
                            ParsedConstant(
                                name=_text(name_n, source) if name_n else "",
                                type_hint=_text(type_n, source) if type_n else "",
                            )
                        )
