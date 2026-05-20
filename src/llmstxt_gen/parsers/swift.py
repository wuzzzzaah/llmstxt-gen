"""Swift parser backed by tree-sitter.

Extracts doc comments, public/internal functions, classes, structs, enums,
protocols, actors, and extensions. Private and fileprivate symbols are
omitted unless the caller opts in via :class:`SwiftParser` ``include_private``.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_swift
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

_SWIFT_LANGUAGE = Language(tree_sitter_swift.language())

_MODIFIERS = "modifiers"
_VISIBILITY_MODIFIER = "visibility_modifier"
_COMMENT = "comment"
_MULTILINE_COMMENT = "multiline_comment"
_NEWLINE = "\n"
_SOURCE_FILE = "source_file"
_IMPORT_DECLARATION = "import_declaration"
_ATTRIBUTE = "attribute"
_FUNCTION_DECLARATION = "function_declaration"
_CLASS_DECLARATION = "class_declaration"
_EXTENSION = "extension"
_PROTOCOL_DECLARATION = "protocol_declaration"
_PROPERTY_DECLARATION = "property_declaration"
_MACRO_DECLARATION = "macro_declaration"
_SIMPLE_IDENTIFIER = "simple_identifier"
_TYPE_CONSTRAINTS = "type_constraints"
_PARAMETER = "parameter"
_ASYNC = "async"
_THROWS = "throws"
_COLON = ":"
_EQUAL = "="
_PATTERN = "pattern"
_TYPE_ANNOTATION = "type_annotation"
_INHERITANCE_SPECIFIER = "inheritance_specifier"
_CLASS_BODY = "class_body"
_ENUM_CLASS_BODY = "enum_class_body"
_INIT_DECLARATION = "init_declaration"
_ENUM_ENTRY = "enum_entry"
_PROTOCOL_BODY = "protocol_body"
_PROTOCOL_FUNCTION_DECLARATION = "protocol_function_declaration"
_PROTOCOL_PROPERTY_DECLARATION = "protocol_property_declaration"
_USER_TYPE = "user_type"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _is_private(node: Node, source: bytes) -> bool:
    modifiers = node.child_by_field_name("modifiers")
    if not modifiers:
        for child in node.children:
            if child.type == _MODIFIERS:
                modifiers = child
                break
    if not modifiers:
        return False
    for child in modifiers.named_children:
        if child.type == _VISIBILITY_MODIFIER:
            txt = _text(child, source)
            if txt in ("private", "fileprivate"):
                return True
    return False


def _get_doc(node: Node, source: bytes) -> str:
    """Extract doc comments (/// or /** ... */) preceding a node."""
    docs: list[str] = []
    curr = node.prev_sibling
    while curr:
        if curr.type in (_COMMENT, _MULTILINE_COMMENT):
            text = _text(curr, source).strip()
            if text.startswith("///"):
                docs.insert(0, text[3:].strip())
            elif text.startswith("/**"):
                inner = text[3:-2].strip()
                docs.insert(0, inner)
            elif text.startswith("//"):
                break
        elif curr.type == _NEWLINE:
            pass
        else:
            break
        curr = curr.prev_sibling

    if node.type == _SOURCE_FILE:
        for child in node.children:
            if child.type == _COMMENT:
                text = _text(child, source).strip()
                if text.startswith("///"):
                    docs.append(text[3:].strip())
            elif child.type == _MULTILINE_COMMENT:
                text = _text(child, source).strip()
                if text.startswith("/**"):
                    docs.append(text[3:-2].strip())
            elif (
                child.type not in (_COMMENT, _MULTILINE_COMMENT, _IMPORT_DECLARATION)
                and child.is_named
            ):
                break

    return "\n".join(docs).strip()


def _get_decorators(node: Node, source: bytes) -> list[str]:
    decorators: list[str] = []
    modifiers = node.child_by_field_name("modifiers")
    if not modifiers:
        for child in node.children:
            if child.type == _MODIFIERS:
                modifiers = child
                break
    if modifiers:
        for child in modifiers.named_children:
            if child.type == _ATTRIBUTE:
                decorators.append(_text(child, source))
    return decorators


class SwiftParser(BaseParser):
    """Parse Swift source via tree-sitter."""

    language = "swift"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_SWIFT_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="swift",
            docstring=_get_doc(root, source),
        )

        classes_by_name: dict[str, ParsedClass] = {}

        for child in root.named_children:
            if child.type == _FUNCTION_DECLARATION:
                if self.include_private or not _is_private(child, source):
                    module.functions.append(self._parse_function(child, source))
            elif child.type == _CLASS_DECLARATION:
                is_extension = any(c.type == _EXTENSION for c in child.children)
                if is_extension:
                    self._handle_extension(child, source, classes_by_name, module)
                elif self.include_private or not _is_private(child, source):
                    cls = self._parse_class(child, source)
                    module.classes.append(cls)
                    classes_by_name[cls.name] = cls
            elif child.type == _PROTOCOL_DECLARATION:
                if self.include_private or not _is_private(child, source):
                    cls = self._parse_protocol(child, source)
                    module.classes.append(cls)
                    classes_by_name[cls.name] = cls
            elif child.type == _PROPERTY_DECLARATION and (
                self.include_private or not _is_private(child, source)
            ):
                module.functions.append(self._parse_property(child, source))
            elif child.type == _MACRO_DECLARATION and (
                self.include_private or not _is_private(child, source)
            ):
                module.functions.append(self._parse_macro(child, source))

        return module

    def _parse_function(self, node: Node, source: bytes) -> ParsedFunction:
        name_node = node.child_by_field_name("name")
        if not name_node:
            for child in node.children:
                if child.type == _SIMPLE_IDENTIFIER:
                    name_node = child
                    break
        name = _text(name_node, source) if name_node else ""

        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            name += _text(type_params, source)

        for child in node.children:
            if child.type == _TYPE_CONSTRAINTS:
                name += " " + _text(child, source)
                break

        params: list[ParsedParameter] = []
        for child in node.children:
            if child.type == _PARAMETER:
                params.append(self._parse_parameter(child, source))

        ret_node = node.child_by_field_name("return_type")
        ret_type = _text(ret_node, source) if ret_node else ""
        if ret_type.startswith("->"):
            ret_type = ret_type[2:].strip()

        is_async = any(c.type == _ASYNC for c in node.children)
        is_throws = any(c.type == _THROWS for c in node.children)
        if is_throws:
            ret_type = f"throws -> {ret_type}" if ret_type else "throws"

        return ParsedFunction(
            name=name,
            parameters=params,
            return_type=ret_type,
            docstring=_get_doc(node, source),
            line=node.start_point[0] + 1,
            is_async=is_async,
            is_private=_is_private(node, source),
            decorators=_get_decorators(node, source),
        )

    def _parse_parameter(self, node: Node, source: bytes) -> ParsedParameter:
        p_name = ""
        p_type = ""
        p_default = ""

        found_colon = False
        found_eq = False
        for c in node.children:
            if c.type == _COLON:
                found_colon = True
                continue
            if c.type == _EQUAL:
                found_eq = True
                continue

            if not found_colon:
                if not c.is_named:
                    continue
                if p_name:
                    p_name += " " + _text(c, source)
                else:
                    p_name = _text(c, source)
            elif not found_eq:
                if c.is_named:
                    p_type = _text(c, source)
            else:
                if c.is_named:
                    p_default = _text(c, source)
        return ParsedParameter(name=p_name, type_hint=p_type, default=p_default)

    def _parse_property(self, node: Node, source: bytes) -> ParsedFunction:
        pattern = node.child_by_field_name("pattern")
        if not pattern:
            for child in node.children:
                if child.type == _PATTERN:
                    pattern = child
                    break

        name = ""
        if pattern:
            for child in pattern.children:
                if child.type == _SIMPLE_IDENTIFIER:
                    name = _text(child, source)
                    break
            if not name:
                name = _text(pattern, source)

        type_node = node.child_by_field_name("type")
        if not type_node:
            for child in node.children:
                if child.type == _TYPE_ANNOTATION:
                    type_node = child
                    break

        type_hint = _text(type_node, source) if type_node else ""
        if type_hint.startswith(":"):
            type_hint = type_hint[1:].strip()

        return ParsedFunction(
            name=name,
            return_type=type_hint,
            docstring=_get_doc(node, source),
            line=node.start_point[0] + 1,
            is_private=_is_private(node, source),
            is_property=True,
            decorators=_get_decorators(node, source),
        )

    def _parse_class(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            name += _text(type_params, source)

        bases: list[str] = []
        for child in node.children:
            if child.type == _INHERITANCE_SPECIFIER:
                bases.append(_text(child, source))

        methods: list[ParsedFunction] = []
        class_vars: list[ParsedConstant] = []

        body = node.child_by_field_name("body")
        if not body:
            for child in node.children:
                if child.type in (_CLASS_BODY, _ENUM_CLASS_BODY):
                    body = child
                    break

        if body:
            for child in body.named_children:
                if child.type == _FUNCTION_DECLARATION:
                    if self.include_private or not _is_private(child, source):
                        methods.append(self._parse_function(child, source))
                elif child.type == _INIT_DECLARATION:
                    if self.include_private or not _is_private(child, source):
                        methods.append(self._parse_init(child, source))
                elif child.type == _PROPERTY_DECLARATION:
                    if self.include_private or not _is_private(child, source):
                        methods.append(self._parse_property(child, source))
                elif child.type == _ENUM_ENTRY:
                    for grandchild in child.named_children:
                        if grandchild.type == _SIMPLE_IDENTIFIER:
                            class_vars.append(ParsedConstant(name=_text(grandchild, source)))

        return ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )

    def _parse_init(self, node: Node, source: bytes) -> ParsedFunction:
        fn = self._parse_function(node, source)
        fn.name = "init"
        return fn

    def _parse_protocol(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        bases: list[str] = []
        for child in node.children:
            if child.type == _INHERITANCE_SPECIFIER:
                bases.append(_text(child, source))

        methods: list[ParsedFunction] = []
        body = node.child_by_field_name("body")
        if not body:
            for child in node.children:
                if child.type == _PROTOCOL_BODY:
                    body = child
                    break
        if body:
            for child in body.named_children:
                if child.type == _PROTOCOL_FUNCTION_DECLARATION:
                    methods.append(self._parse_function(child, source))
                elif child.type == _PROTOCOL_PROPERTY_DECLARATION:
                    pattern = child.child_by_field_name("pattern")
                    if not pattern:
                        for c in child.children:
                            if c.type == _PATTERN:
                                pattern = c
                                break
                    name_str = ""
                    if pattern:
                        for c in pattern.children:
                            if c.type == _SIMPLE_IDENTIFIER:
                                name_str = _text(c, source)
                                break
                        if not name_str:
                            name_str = _text(pattern, source)

                    type_node = child.child_by_field_name("type")
                    if not type_node:
                        for c in child.children:
                            if c.type == _TYPE_ANNOTATION:
                                type_node = c
                                break
                    type_str = _text(type_node, source) if type_node else ""
                    if type_str.startswith(":"):
                        type_str = type_str[1:].strip()
                    methods.append(
                        ParsedFunction(
                            name=name_str,
                            return_type=type_str,
                            docstring=_get_doc(child, source),
                            line=child.start_point[0] + 1,
                            is_property=True,
                        )
                    )
        return ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            bases=bases,
            methods=methods,
            line=node.start_point[0] + 1,
        )

    def _handle_extension(
        self, node: Node, source: bytes, classes: dict[str, ParsedClass], module: ParsedModule
    ) -> None:
        type_node = node.child_by_field_name("name")
        if not type_node:
            for child in node.children:
                if child.type == _USER_TYPE:
                    type_node = child
                    break
        if not type_node:
            return
        type_name = _text(type_node, source)

        if type_name in classes:
            cls = classes[type_name]
        else:
            cls = ParsedClass(name=f"extension {type_name}", line=node.start_point[0] + 1)
            module.classes.append(cls)

        body = node.child_by_field_name("body")
        if not body:
            for child in node.children:
                if child.type == _CLASS_BODY:
                    body = child
                    break
        if body:
            for child in body.named_children:
                if child.type == _FUNCTION_DECLARATION:
                    if self.include_private or not _is_private(child, source):
                        cls.methods.append(self._parse_function(child, source))
                elif child.type == _PROPERTY_DECLARATION and (
                    self.include_private or not _is_private(child, source)
                ):
                    cls.methods.append(self._parse_property(child, source))
                elif child.type == _INIT_DECLARATION and (
                    self.include_private or not _is_private(child, source)
                ):
                    cls.methods.append(self._parse_init(child, source))

    def _parse_macro(self, node: Node, source: bytes) -> ParsedFunction:
        fn = self._parse_function(node, source)
        fn.decorators.append("@macro")
        return fn
