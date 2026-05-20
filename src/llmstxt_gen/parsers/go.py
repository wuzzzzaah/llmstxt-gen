"""Go parser backed by tree-sitter.

Extracts package docstrings, exported functions, structs, interfaces, and
constants/variables. Non-exported symbols (starting with lowercase) are
skipped unless ``include_private`` is set on the parser.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_go
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

_GO_LANGUAGE = Language(tree_sitter_go.language())

_COMMENT = "comment"
_PARAMETER_DECLARATION = "parameter_declaration"
_IDENTIFIER = "identifier"
_UNDERSCORE = "_"
_VARIADIC_PARAMETER_DECLARATION = "variadic_parameter_declaration"
_TYPE_IDENTIFIER = "type_identifier"
_PACKAGE_IDENTIFIER = "package_identifier"
_PACKAGE_CLAUSE = "package_clause"
_FUNCTION_DECLARATION = "function_declaration"
_METHOD_DECLARATION = "method_declaration"
_TYPE_DECLARATION = "type_declaration"
_TYPE_SPEC = "type_spec"
_TYPE_ALIAS = "type_alias"
_CONST_DECLARATION = "const_declaration"
_VAR_DECLARATION = "var_declaration"
_CONST_SPEC = "const_spec"
_VAR_SPEC = "var_spec"
_CONST_SPEC_LIST = "const_spec_list"
_VAR_SPEC_LIST = "var_spec_list"
_STRUCT_TYPE = "struct_type"
_FIELD_DECLARATION_LIST = "field_declaration_list"
_FIELD_DECLARATION = "field_declaration"
_FIELD_IDENTIFIER = "field_identifier"
_INTERFACE_TYPE = "interface_type"
_TYPE_ELEM = "type_elem"
_METHOD_ELEM = "method_elem"
_METHOD_SPEC = "method_spec"
_PARAMETER_LIST = "parameter_list"
_QUALIFIED_TYPE = "qualified_type"
_POINTER_TYPE = "pointer_type"
_ARRAY_TYPE = "array_type"
_MAP_TYPE = "map_type"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _is_exported(name: str) -> bool:
    return bool(name and name[0].isupper())


def _get_doc(node: Node, source: bytes) -> str:
    docs: list[str] = []
    prev = node.prev_sibling
    # In Go, comments above a declaration are doc comments.
    # They are separate nodes in tree-sitter-go.
    while prev and prev.type == _COMMENT:
        text = _text(prev, source).strip()
        if text.startswith("//") or text.startswith("/*"):
            docs.insert(0, clean_docstring(text))
        prev = prev.prev_sibling
    return "\n".join(docs).strip()


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if params_node is None:
        return []
    params: list[ParsedParameter] = []
    # params_node is usually (parameter_list)
    for child in params_node.named_children:
        if child.type == _PARAMETER_DECLARATION:
            # child has (identifier) and (type_identifier) or similar
            type_node = child.child_by_field_name("type")
            type_hint = _text(type_node, source) if type_node else ""
            # Can have multiple identifiers for one type: func(a, b int)
            names = [
                _text(n, source)
                for n in child.named_children
                if n.type in (_IDENTIFIER, _UNDERSCORE)
            ]
            if not names:
                # Anonymous parameter: func(int)
                params.append(ParsedParameter(name="", type_hint=type_hint))
            for name in names:
                params.append(ParsedParameter(name=name, type_hint=type_hint))
        elif child.type == _VARIADIC_PARAMETER_DECLARATION:
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            params.append(
                ParsedParameter(
                    name=f"...{_text(name_node, source)}" if name_node else "...",
                    type_hint=f"...{_text(type_node, source)}" if type_node else "...",
                )
            )
    return params


def _parse_result(result_node: Node | None, source: bytes) -> str:
    if result_node is None:
        return ""
    # result can be (type_identifier) or (parameter_list) for multiple returns
    return _text(result_node, source)


def _find_type_identifier(node: Node) -> Node | None:
    if node.type in (_TYPE_IDENTIFIER, _PACKAGE_IDENTIFIER):
        return node
    for child in node.children:
        res = _find_type_identifier(child)
        if res:
            return res
    return None


class GoParser(BaseParser):
    """Parse Go source via tree-sitter."""

    language = "go"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_GO_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        # Package docstring
        package_node = None
        for child in root.named_children:
            if child.type == _PACKAGE_CLAUSE:
                package_node = child
                break

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="go",
            docstring=_get_doc(package_node, source) if package_node else "",
        )

        # We'll collect methods and attach them to classes later if they exist,
        # or just keep them in a temporary store.
        methods_by_receiver: dict[str, list[ParsedFunction]] = {}

        for child in root.named_children:
            if child.type == _FUNCTION_DECLARATION:
                fn = self._parse_function(child, source)
                if self.include_private or _is_exported(fn.name):
                    module.functions.append(fn)

            elif child.type == _METHOD_DECLARATION:
                fn = self._parse_method(child, source)
                receiver_node = child.child_by_field_name("receiver")
                if receiver_node:
                    tid = _find_type_identifier(receiver_node)
                    if tid:
                        rcv_type = _text(tid, source)
                        if self.include_private or _is_exported(fn.name):
                            methods_by_receiver.setdefault(rcv_type, []).append(fn)

            elif child.type == _TYPE_DECLARATION:
                for spec in child.named_children:
                    if spec.type in (_TYPE_SPEC, _TYPE_ALIAS):
                        cls = self._parse_type_spec(spec, source)
                        if self.include_private or _is_exported(cls.name):
                            module.classes.append(cls)

            elif child.type in (_CONST_DECLARATION, _VAR_DECLARATION):
                specs = []
                for sub in child.named_children:
                    if sub.type in (_CONST_SPEC, _VAR_SPEC):
                        specs.append(sub)
                    elif sub.type in (_CONST_SPEC_LIST, _VAR_SPEC_LIST):
                        for spec in sub.named_children:
                            if spec.type in (_CONST_SPEC, _VAR_SPEC):
                                specs.append(spec)

                for spec in specs:
                    # const ( a, b = 1, 2 )
                    # tree-sitter-go: const_spec has 'name' (identifiers) and 'type' and 'values'
                    type_node = spec.child_by_field_name("type")
                    type_hint = _text(type_node, source) if type_node else ""

                    # In const_spec/var_spec, identifiers are just children usually,
                    # but some might be field 'name'.
                    names = [n for n in spec.named_children if n.type == _IDENTIFIER]
                    for name_node in names:
                        name = _text(name_node, source)
                        if self.include_private or _is_exported(name):
                            module.constants.append(ParsedConstant(name=name, type_hint=type_hint))

        # Attach methods to classes
        for cls in module.classes:
            if cls.name in methods_by_receiver:
                cls.methods.extend(methods_by_receiver.pop(cls.name))

        # Any methods left for receivers that weren't defined in this file (or aren't structs/interfaces)
        # We might want to keep them or discard them. The requirements say:
        # "Exported methods on receivers, attached to their receiver type"
        # If the type is not in the same file, we can't easily attach it to a ParsedClass
        # unless we create a dummy ParsedClass.
        for rcv_type, methods in methods_by_receiver.items():
            # If we don't have the class, create one.
            module.classes.append(
                ParsedClass(
                    name=rcv_type,
                    methods=methods,
                )
            )

        return module

    def _parse_function(self, node: Node, source: bytes) -> ParsedFunction:
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        result_node = node.child_by_field_name("result")
        name = _text(name_node, source) if name_node else ""
        return ParsedFunction(
            name=name,
            parameters=_parse_parameters(params_node, source),
            return_type=_parse_result(result_node, source),
            docstring=_get_doc(node, source),
            line=node.start_point[0] + 1,
            is_private=not _is_exported(name),
        )

    def _parse_method(self, node: Node, source: bytes) -> ParsedFunction:
        # method_declaration is almost same as function_declaration but with receiver
        return self._parse_function(node, source)

    def _parse_type_spec(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        name = _text(name_node, source) if name_node else ""

        docstring = _get_doc(node, source)
        if (
            not docstring
            and node.parent
            and node.parent.type == _TYPE_DECLARATION
            and len([c for c in node.parent.named_children if c.type == _TYPE_SPEC]) == 1
        ):
            # Try parent if it's a single type decl: type Foo struct {}
            docstring = _get_doc(node.parent, source)

        bases: list[str] = []
        methods: list[ParsedFunction] = []

        if type_node:
            if type_node.type == _STRUCT_TYPE:
                # field_declaration_list is often a child of struct_type, but not necessarily by field name 'fields'
                # in my exploration it was field_declaration_list
                field_list = type_node.child_by_field_name("fields")
                if not field_list:
                    # Fallback to finding by type if field_by_name failed
                    for c in type_node.children:
                        if c.type == _FIELD_DECLARATION_LIST:
                            field_list = c
                            break

                if field_list:
                    for field in field_list.named_children:
                        if (
                            field.type == _FIELD_DECLARATION
                            and not field.child_by_field_name("name")
                            and not any(c.type == _FIELD_IDENTIFIER for c in field.children)
                        ):
                            # check for anonymous/embedded fields
                            # usually they don't have a name field
                            # If it doesn't have field_identifier, it's likely embedded
                            bases.append(_text(field, source))
            elif type_node.type == _INTERFACE_TYPE:
                # In tree-sitter-go, the methods/embedded types are named children of interface_type
                for child in type_node.named_children:
                    if child.type == _TYPE_ELEM:
                        tid = _find_type_identifier(child)
                        if tid:
                            bases.append(_text(tid, source))
                    elif child.type in (_METHOD_ELEM, _METHOD_SPEC):
                        # Extract as a function
                        fn_name_node = child.child_by_field_name("name")
                        params_node = child.child_by_field_name("parameters")
                        result_node = child.child_by_field_name("result")

                        # Fallback for method_elem which might not have field names set up the same way
                        if not fn_name_node:
                            for c in child.named_children:
                                if c.type == _FIELD_IDENTIFIER:
                                    fn_name_node = c
                                    break
                        if not params_node:
                            for c in child.named_children:
                                if c.type == _PARAMETER_LIST:
                                    params_node = c
                                    break
                        if not result_node:
                            # result is usually the last child if it's a type or parameter_list
                            # but let's be careful.
                            potential_result = (
                                child.named_children[-1] if child.named_children else None
                            )
                            if (
                                potential_result
                                and potential_result.type
                                in (
                                    _TYPE_IDENTIFIER,
                                    _PARAMETER_LIST,
                                    _QUALIFIED_TYPE,
                                    _POINTER_TYPE,
                                    _ARRAY_TYPE,
                                    _MAP_TYPE,
                                )
                                and potential_result != fn_name_node
                                and potential_result != params_node
                            ):
                                result_node = potential_result

                        fn_name = _text(fn_name_node, source) if fn_name_node else ""
                        if self.include_private or _is_exported(fn_name):
                            methods.append(
                                ParsedFunction(
                                    name=fn_name,
                                    parameters=_parse_parameters(params_node, source),
                                    return_type=_parse_result(result_node, source),
                                    docstring=_get_doc(child, source),
                                    line=child.start_point[0] + 1,
                                    is_private=not _is_exported(fn_name),
                                )
                            )

        return ParsedClass(
            name=name,
            docstring=docstring,
            bases=bases,
            methods=methods,
            line=node.start_point[0] + 1,
        )
