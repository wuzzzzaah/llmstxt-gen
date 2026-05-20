"""C/C++ parser backed by tree-sitter-cpp.

Extracts functions, classes, structs, enums, typedefs, and constants.
Handles Doxygen-style comments and C++ visibility modifiers.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from llmstxt_gen.parsers.base import (
    BaseParser,
    ParsedClass,
    ParsedConstant,
    ParsedFunction,
    ParsedModule,
    ParsedParameter,
    clean_docstring,
)
from llmstxt_gen.walker import SourceFile

_CPP_LANGUAGE = Language(tree_sitter_cpp.language())

_TEMPLATE_DECLARATION = "template_declaration"
_COMMENT = "comment"
_TEMPLATE_PARAMETER_LIST = "template_parameter_list"
_CLASS_SPECIFIER = "class_specifier"
_STRUCT_SPECIFIER = "struct_specifier"
_UNION_SPECIFIER = "union_specifier"
_FUNCTION_DEFINITION = "function_definition"
_DECLARATION = "declaration"
_ACCESS_SPECIFIER = "access_specifier"
_FIELD_DECLARATION_LIST = "field_declaration_list"
_FIELD_DECLARATION = "field_declaration"
_ENUM_SPECIFIER = "enum_specifier"
_TYPE_DEFINITION = "type_definition"
_ALIAS_DECLARATION = "alias_declaration"
_FUNCTION_DECLARATOR = "function_declarator"
_POINTER_DECLARATOR = "pointer_declarator"
_REFERENCE_DECLARATOR = "reference_declarator"
_INIT_DECLARATOR = "init_declarator"
_STORAGE_CLASS_SPECIFIER = "storage_class_specifier"
_PARAMETER_DECLARATION = "parameter_declaration"
_OPTIONAL_PARAMETER_DECLARATION = "optional_parameter_declaration"
_BASE_CLASS_SPECIFIER = "base_class_specifier"
_ENUMERATOR = "enumerator"
_IDENTIFIER = "identifier"
_FIELD_IDENTIFIER = "field_identifier"
_TYPE_IDENTIFIER = "type_identifier"
_OPERATOR_NAME = "operator_name"
_QUALIFIED_IDENTIFIER = "qualified_identifier"
_DESTRUCTOR_NAME = "destructor_name"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_doc(node: Node, source: bytes) -> str:
    """Extract Doxygen-style comments (/** ... */ and /// ...) above a node."""
    docs: list[str] = []
    target = node
    if node.parent and node.parent.type == _TEMPLATE_DECLARATION:
        target = node.parent

    curr = target.prev_sibling
    while curr:
        if curr.type == _COMMENT:
            text = _text(curr, source).strip()
            if text.startswith("/**") or text.startswith("///"):
                docs.insert(0, clean_docstring(text))
            else:
                # Stop at regular comments
                break
        elif not curr.is_named:
            # Skip whitespace/punctuation
            curr = curr.prev_sibling
            continue
        else:
            break
        curr = curr.prev_sibling

    return "\n".join(docs).strip()


class CppParser(BaseParser):
    """Parse C/C++ source via tree-sitter."""

    language = "cpp"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_CPP_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="cpp",
            docstring="",
        )

        self._parse_nodes(root.children, source, module)
        return module

    def _parse_nodes(
        self,
        nodes: list[Node],
        source: bytes,
        module: ParsedModule | None,
        current_class: ParsedClass | None = None,
        default_visibility: str = "public",
    ) -> None:
        # Default visibility
        visibility = default_visibility

        for node in nodes:
            actual_node = node
            template_params = ""
            if node.type == _TEMPLATE_DECLARATION:
                # Find template_parameter_list
                for child in node.children:
                    if child.type == _TEMPLATE_PARAMETER_LIST:
                        template_params = _text(child, source)
                    elif child.type in (
                        _CLASS_SPECIFIER,
                        _STRUCT_SPECIFIER,
                        _UNION_SPECIFIER,
                        _FUNCTION_DEFINITION,
                        _DECLARATION,
                    ):
                        actual_node = child

            if actual_node.type == _ACCESS_SPECIFIER:
                visibility = _text(actual_node, source).strip().rstrip(":")
                continue

            if actual_node.type == _FIELD_DECLARATION_LIST:
                self._parse_nodes(actual_node.children, source, module, current_class, visibility)
                continue

            if actual_node.type in (_FUNCTION_DEFINITION, _DECLARATION, _FIELD_DECLARATION):
                is_func = False
                decl = actual_node.child_by_field_name("declarator")
                if decl and self._is_function_declarator(decl):
                    is_func = True

                if is_func:
                    fn = self._parse_function(actual_node, source)
                    if template_params:
                        fn.name = f"template{template_params} {fn.name}"

                    is_private = (visibility in ("private", "protected") and current_class) or (
                        not current_class and self._is_static(node, source)
                    )

                    if self.include_private or not is_private:
                        if current_class:
                            fn.is_private = visibility in ("private", "protected")
                            current_class.methods.append(fn)
                        elif module:
                            module.functions.append(fn)
                else:
                    self._handle_declaration(actual_node, source, module, current_class, visibility)

            elif actual_node.type in (_CLASS_SPECIFIER, _STRUCT_SPECIFIER, _UNION_SPECIFIER):
                cls = self._parse_class(actual_node, source, module, template_params)
                is_private = (visibility in ("private", "protected") and current_class) or (
                    not current_class and self._is_static(node, source)
                )
                if (self.include_private or not is_private) and module:
                    module.classes.append(cls)

            elif actual_node.type == _ENUM_SPECIFIER:
                cls = self._parse_enum(actual_node, source)
                is_private = (visibility in ("private", "protected") and current_class) or (
                    not current_class and self._is_static(node, source)
                )
                if (self.include_private or not is_private) and module:
                    module.classes.append(cls)

            elif actual_node.type in (_TYPE_DEFINITION, _ALIAS_DECLARATION):
                if module:
                    self._handle_type_alias(actual_node, source, module)

    def _is_function_declarator(self, node: Node) -> bool:
        if node.type == _FUNCTION_DECLARATOR:
            return True
        if node.type in (_POINTER_DECLARATOR, _REFERENCE_DECLARATOR, _INIT_DECLARATOR):
            child = node.child_by_field_name("declarator")
            return self._is_function_declarator(child) if child else False
        return False

    def _is_static(self, node: Node, source: bytes) -> bool:
        for child in node.children:
            if child.type == _STORAGE_CLASS_SPECIFIER and _text(child, source) == "static":
                return True
        return False

    def _parse_function(self, node: Node, source: bytes) -> ParsedFunction:
        type_node = node.child_by_field_name("type")
        decl_node = node.child_by_field_name("declarator")

        curr = decl_node
        while curr and curr.type != _FUNCTION_DECLARATOR:
            next_node = curr.child_by_field_name("declarator")
            if not next_node:
                break
            curr = next_node

        name = ""
        params: list[ParsedParameter] = []
        if curr and curr.type == _FUNCTION_DECLARATOR:
            name_node = curr.child_by_field_name("declarator")
            if name_node:
                name = self._extract_identifier(name_node, source)

            params_node = curr.child_by_field_name("parameters")
            if params_node:
                for p in params_node.named_children:
                    if p.type in (_PARAMETER_DECLARATION, _OPTIONAL_PARAMETER_DECLARATION):
                        p_name = ""
                        p_type = ""
                        p_default = ""

                        p_type_node = p.child_by_field_name("type")
                        p_decl_node = p.child_by_field_name("declarator")

                        if p_type_node:
                            p_type = _text(p_type_node, source)
                        if p_decl_node:
                            p_name = self._extract_identifier(p_decl_node, source)

                        if p.type == _OPTIONAL_PARAMETER_DECLARATION:
                            p_val_node = p.child_by_field_name("default_value")
                            if p_val_node:
                                p_default = _text(p_val_node, source)

                        params.append(ParsedParameter(name=p_name, type_hint=p_type, default=p_default))

        return_type = _text(type_node, source) if type_node else ""

        return ParsedFunction(
            name=name,
            parameters=params,
            return_type=return_type,
            docstring=_get_doc(node, source),
            line=node.start_point[0] + 1,
        )

    def _parse_class(self, node: Node, source: bytes, module: ParsedModule | None, template_params: str = "") -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else "anonymous"
        if template_params:
            name = f"{name}{template_params}"

        bases: list[str] = []
        base_clause = node.child_by_field_name("base_class_clause")
        if base_clause:
            for child in base_clause.named_children:
                if child.type == _BASE_CLASS_SPECIFIER:
                    bases.append(_text(child, source))

        cls = ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            bases=bases,
            line=node.start_point[0] + 1,
        )

        body = node.child_by_field_name("body")
        if body:
            default_visibility = "public" if node.type == _STRUCT_SPECIFIER else "private"
            self._parse_class_body(body, source, module, cls, default_visibility)

        return cls

    def _parse_class_body(self, body: Node, source: bytes, module: ParsedModule | None, cls: ParsedClass, default_visibility: str) -> None:
        self._parse_nodes([body], source, module, cls, default_visibility)

    def _parse_enum(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else "anonymous"

        class_vars: list[ParsedConstant] = []
        body = node.child_by_field_name("body")
        if body:
            for variant in body.named_children:
                if variant.type == _ENUMERATOR:
                    v_name = variant.child_by_field_name("name")
                    v_val = variant.child_by_field_name("value")
                    class_vars.append(
                        ParsedConstant(
                            name=_text(v_name, source) if v_name else "",
                            value=_text(v_val, source) if v_val else "",
                        )
                    )

        return ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )

    def _handle_declaration(self, node: Node, source: bytes, module: ParsedModule | None, current_class: ParsedClass | None, visibility: str) -> None:
        type_node = node.child_by_field_name("type")
        if not type_node:
            return

        is_private = (visibility in ("private", "protected") and current_class) or (not current_class and self._is_static(node, source))

        if not self.include_private and is_private:
            return

        for child in node.named_children:
            if child.type in (
                _IDENTIFIER,
                _FIELD_IDENTIFIER,
                _INIT_DECLARATOR,
                _POINTER_DECLARATOR,
                _REFERENCE_DECLARATOR,
            ):
                name = self._extract_identifier(child, source)
                if not name:
                    continue

                val = ""
                if child.type == _INIT_DECLARATOR:
                    val_node = child.child_by_field_name("value")
                    if val_node:
                        val = _text(val_node, source)

                const = ParsedConstant(
                    name=name,
                    type_hint=_text(type_node, source),
                    value=val
                )

                if current_class:
                    current_class.class_vars.append(const)
                elif module:
                    module.constants.append(const)

    def _handle_type_alias(self, node: Node, source: bytes, module: ParsedModule) -> None:
        if node.type == _TYPE_DEFINITION:
            # Find declarator which contains the name
            decl = node.child_by_field_name("declarator")
            type_node = node.child_by_field_name("type")
            if decl and type_node:
                module.constants.append(ParsedConstant(
                    name=self._extract_identifier(decl, source),
                    type_hint=_text(type_node, source)
                ))
        elif node.type == _ALIAS_DECLARATION:
            name_node = node.child_by_field_name("name")
            type_node = node.child_by_field_name("type")
            if name_node and type_node:
                module.constants.append(ParsedConstant(
                    name=_text(name_node, source),
                    type_hint=_text(type_node, source)
                ))

    def _extract_identifier(self, node: Node, source: bytes) -> str:
        if node.type in (_IDENTIFIER, _FIELD_IDENTIFIER, _TYPE_IDENTIFIER):
            return _text(node, source)

        if node.type == _OPERATOR_NAME:
            return _text(node, source)

        if node.type == _QUALIFIED_IDENTIFIER:
            return _text(node, source)

        if node.type == _DESTRUCTOR_NAME:
            return _text(node, source)

        decl = node.child_by_field_name("declarator")
        if decl:
            return self._extract_identifier(decl, source)

        for child in node.named_children:
            res = self._extract_identifier(child, source)
            if res:
                return res
        return ""
