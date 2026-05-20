"""C# parser backed by tree-sitter.

Extracts XML doc comments, public/protected classes, structs, interfaces,
records, enums, and their members.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_c_sharp
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

_CS_LANGUAGE = Language(tree_sitter_c_sharp.language())

_COMMENT = "comment"
_MODIFIER = "modifier"
_INTERFACE_DECLARATION = "interface_declaration"
_ATTRIBUTE_LIST = "attribute_list"
_ATTRIBUTE = "attribute"
_TYPE_PARAMETER_CONSTRAINTS_CLAUSE = "type_parameter_constraints_clause"
_PARAMETER = "parameter"
_NAMESPACE_DECLARATION = "namespace_declaration"
_FILE_SCOPED_NAMESPACE_DECLARATION = "file_scoped_namespace_declaration"
_USING_DIRECTIVE = "using_directive"
_CLASS_DECLARATION = "class_declaration"
_STRUCT_DECLARATION = "struct_declaration"
_RECORD_DECLARATION = "record_declaration"
_ENUM_DECLARATION = "enum_declaration"
_METHOD_DECLARATION = "method_declaration"
_PROPERTY_DECLARATION = "property_declaration"
_FIELD_DECLARATION = "field_declaration"
_EVENT_DECLARATION = "event_declaration"
_EVENT_FIELD_DECLARATION = "event_field_declaration"
_IDENTIFIER = "identifier"
_GENERIC_NAME = "generic_name"
_QUALIFIED_NAME = "qualified_name"
_PARAMETER_LIST = "parameter_list"
_ENUM_MEMBER_DECLARATION = "enum_member_declaration"
_VARIABLE_DECLARATION = "variable_declaration"
_VARIABLE_DECLARATOR = "variable_declarator"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_xml_doc(node: Node, source: bytes) -> str:
    docs: list[str] = []
    curr = node.prev_sibling
    while curr and curr.type == _COMMENT:
        text = _text(curr, source).strip()
        if text.startswith("///"):
            docs.insert(0, text[3:].strip())
        curr = curr.prev_sibling
    return "\n".join(docs).strip()


def _get_modifiers(node: Node, source: bytes) -> list[str]:
    mods = []
    for child in node.children:
        if child.type == _MODIFIER:
            # Some modifiers are nested nodes
            mods.append(_text(child, source))
    return mods


def _is_exported(node: Node, source: bytes) -> bool:
    # Interface members are implicitly public
    if node.parent and node.parent.parent and node.parent.parent.type == _INTERFACE_DECLARATION:
        return True
    mods = _get_modifiers(node, source)
    return "public" in mods or "protected" in mods


def _get_attributes(node: Node, source: bytes) -> list[str]:
    attrs = []
    for child in node.children:
        if child.type == _ATTRIBUTE_LIST:
            for attr in child.named_children:
                if attr.type == _ATTRIBUTE:
                    attrs.append(_text(attr, source))
    return attrs


def _get_type_constraints(node: Node, source: bytes) -> str:
    constraints = []
    for child in node.children:
        if child.type == _TYPE_PARAMETER_CONSTRAINTS_CLAUSE:
            constraints.append(_text(child, source))
    return " ".join(constraints)


def _parse_parameters(node: Node, source: bytes) -> list[ParsedParameter]:
    params = []
    for child in node.named_children:
        if child.type == _PARAMETER:
            type_node = child.child_by_field_name("type")
            name_node = child.child_by_field_name("name")
            default_node = child.child_by_field_name("default")
            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    type_hint=_text(type_node, source) if type_node else "",
                    default=_text(default_node, source) if default_node else "",
                )
            )
    return params


class CSharpParser(BaseParser):
    """Parse C# source via tree-sitter.

    C# properties map to a single ParsedFunction flagged as is_property=True.
    Partial classes in the same file are merged.
    """

    language = "csharp"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_CS_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="csharp",
        )

        self._collect_members(root, source, module)
        return module

    def _collect_members(
        self, node: Node, source: bytes, parent: ParsedModule | ParsedClass
    ) -> None:
        for child in node.named_children:
            if child.type in (_NAMESPACE_DECLARATION, _FILE_SCOPED_NAMESPACE_DECLARATION):
                # recurse into namespace body or siblings for file_scoped
                if child.type == _NAMESPACE_DECLARATION:
                    body = child.child_by_field_name("body")
                    if body:
                        self._collect_members(body, source, parent)
                else:
                    # file_scoped_namespace_declaration: everything after it is in the namespace
                    # In tree-sitter-c-sharp, the members are usually siblings or children
                    # Actually for file_scoped, members ARE children of the declaration node in TS
                    for grandchild in child.named_children:
                        if grandchild.type not in (_MODIFIER, _IDENTIFIER, _USING_DIRECTIVE):
                            self._collect_members_node(grandchild, source, parent)
            else:
                self._collect_members_node(child, source, parent)

    def _collect_members_node(
        self, child: Node, source: bytes, parent: ParsedModule | ParsedClass
    ) -> None:
        if child.type in (
            _CLASS_DECLARATION,
            _STRUCT_DECLARATION,
            _INTERFACE_DECLARATION,
            _RECORD_DECLARATION,
        ):
            if self.include_private or _is_exported(child, source):
                self._parse_class_like(child, source, parent)
        elif child.type == _ENUM_DECLARATION:
            if self.include_private or _is_exported(child, source):
                self._parse_enum(child, source, parent)
        elif child.type == _METHOD_DECLARATION:
            if self.include_private or _is_exported(child, source):
                self._parse_method(child, source, parent)
        elif child.type == _PROPERTY_DECLARATION:
            if self.include_private or _is_exported(child, source):
                self._parse_property(child, source, parent)
        elif child.type == _FIELD_DECLARATION:
            if self.include_private or _is_exported(child, source):
                self._parse_field(child, source, parent)
        elif child.type == _EVENT_DECLARATION:
            if self.include_private or _is_exported(child, source):
                self._parse_event(child, source, parent)
        elif child.type == _EVENT_FIELD_DECLARATION and (
            self.include_private or _is_exported(child, source)
        ):
            self._parse_field(child, source, parent, is_event=True)

    def _parse_class_like(
        self, node: Node, source: bytes, parent: ParsedModule | ParsedClass
    ) -> None:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        is_partial = "partial" in _get_modifiers(node, source)
        target_class = None

        if is_partial and isinstance(parent, ParsedModule):
            for cls in parent.classes:
                if cls.name == name:
                    target_class = cls
                    break

        if target_class is None:
            bases = []
            base_list = node.child_by_field_name("base_list")
            if base_list:
                for base in base_list.named_children:
                    if base.type in (_IDENTIFIER, _GENERIC_NAME, _QUALIFIED_NAME):
                        bases.append(_text(base, source))

            target_class = ParsedClass(
                name=name,
                docstring=_get_xml_doc(node, source),
                bases=bases,
                line=node.start_point[0] + 1,
            )
            if isinstance(parent, ParsedModule):
                parent.classes.append(target_class)

        # Add members
        body = node.child_by_field_name("body")
        if body:
            self._collect_members(body, source, target_class)

        # Handle record positional parameters as class_vars
        if node.type == _RECORD_DECLARATION:
            params_node = None
            for child in node.children:
                if child.type == _PARAMETER_LIST:
                    params_node = child
                    break
            if params_node:
                params = _parse_parameters(params_node, source)
                for p in params:
                    target_class.class_vars.append(
                        ParsedConstant(name=p.name, type_hint=p.type_hint)
                    )

    def _parse_enum(self, node: Node, source: bytes, parent: ParsedModule | ParsedClass) -> None:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        enum_class = ParsedClass(
            name=name, docstring=_get_xml_doc(node, source), line=node.start_point[0] + 1
        )

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                if member.type == _ENUM_MEMBER_DECLARATION:
                    m_name_node = member.child_by_field_name("name")
                    m_name = _text(m_name_node, source) if m_name_node else ""
                    enum_class.class_vars.append(ParsedConstant(name=m_name))

        if isinstance(parent, ParsedModule):
            parent.classes.append(enum_class)

    def _parse_method(self, node: Node, source: bytes, parent: ParsedModule | ParsedClass) -> None:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        params_node = node.child_by_field_name("parameters")
        returns_node = node.child_by_field_name("returns")

        type_params = node.child_by_field_name("type_parameters")
        type_params_text = _text(type_params, source) if type_params else ""

        constraints = _get_type_constraints(node, source)

        full_name = name + type_params_text
        if constraints:
            full_name += " " + constraints

        fn = ParsedFunction(
            name=full_name,
            parameters=_parse_parameters(params_node, source) if params_node else [],
            return_type=_text(returns_node, source) if returns_node else "",
            docstring=_get_xml_doc(node, source),
            line=node.start_point[0] + 1,
            is_async="async" in _get_modifiers(node, source),
            decorators=_get_attributes(node, source),
            is_private=not _is_exported(node, source),
        )

        if isinstance(parent, ParsedModule):
            parent.functions.append(fn)
        else:
            parent.methods.append(fn)

    def _parse_property(
        self, node: Node, source: bytes, parent: ParsedModule | ParsedClass
    ) -> None:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""
        type_node = node.child_by_field_name("type")

        fn = ParsedFunction(
            name=name,
            return_type=_text(type_node, source) if type_node else "",
            docstring=_get_xml_doc(node, source),
            line=node.start_point[0] + 1,
            is_property=True,
            decorators=_get_attributes(node, source),
            is_private=not _is_exported(node, source),
        )

        if isinstance(parent, ParsedModule):
            parent.functions.append(fn)
        else:
            parent.methods.append(fn)

    def _parse_field(
        self,
        node: Node,
        source: bytes,
        parent: ParsedModule | ParsedClass,
        is_event: bool = False,
    ) -> None:
        var_decl = node.child_by_field_name("declaration")
        if not var_decl:
            for child in node.children:
                if child.type == _VARIABLE_DECLARATION:
                    var_decl = child
                    break

        if var_decl:
            type_node = var_decl.child_by_field_name("type")
            type_hint = _text(type_node, source) if type_node else ""

            for child in var_decl.named_children:
                if child.type == _VARIABLE_DECLARATOR:
                    name_node = child.child_by_field_name("name")
                    name = _text(name_node, source) if name_node else ""

                    if is_event:
                        fn = ParsedFunction(
                            name=name,
                            return_type=type_hint,
                            docstring=_get_xml_doc(node, source),
                            line=node.start_point[0] + 1,
                            is_property=True,
                            decorators=_get_attributes(node, source) + ["event"],
                            is_private=not _is_exported(node, source),
                        )
                        if isinstance(parent, ParsedModule):
                            parent.functions.append(fn)
                        else:
                            parent.methods.append(fn)
                    else:
                        const = ParsedConstant(
                            name=name,
                            type_hint=type_hint,
                        )
                        if isinstance(parent, ParsedModule):
                            parent.constants.append(const)
                        else:
                            parent.class_vars.append(const)

    def _parse_event(self, node: Node, source: bytes, parent: ParsedModule | ParsedClass) -> None:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""
        type_node = node.child_by_field_name("type")

        fn = ParsedFunction(
            name=name,
            return_type=_text(type_node, source) if type_node else "",
            docstring=_get_xml_doc(node, source),
            line=node.start_point[0] + 1,
            is_property=True,
            decorators=_get_attributes(node, source) + ["event"],
            is_private=not _is_exported(node, source),
        )
        if isinstance(parent, ParsedModule):
            parent.functions.append(fn)
        else:
            parent.methods.append(fn)
