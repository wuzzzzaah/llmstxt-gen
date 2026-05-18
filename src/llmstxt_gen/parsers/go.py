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
)
from llmstxt_gen.walker import SourceFile

_GO_LANGUAGE = Language(tree_sitter_go.language())


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _is_exported(name: str) -> bool:
    return bool(name and name[0].isupper())


def _get_doc(node: Node, source: bytes) -> str:
    docs: list[str] = []
    prev = node.prev_sibling
    # In Go, comments above a declaration are doc comments.
    # They are separate nodes in tree-sitter-go.
    while prev and prev.type == "comment":
        text = _text(prev, source).strip()
        if text.startswith("//"):
            docs.insert(0, text[2:].strip())
        elif text.startswith("/*"):
            # Multi-line comment /* ... */
            inner = text[2:-2].strip()
            lines = [ln.strip().lstrip("*").strip() for ln in inner.splitlines()]
            docs.insert(0, "\n".join(ln for ln in lines if ln))
        prev = prev.prev_sibling
    return "\n".join(docs).strip()


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if params_node is None:
        return []
    params: list[ParsedParameter] = []
    # params_node is usually (parameter_list)
    for child in params_node.named_children:
        if child.type == "parameter_declaration":
            # child has (identifier) and (type_identifier) or similar
            type_node = child.child_by_field_name("type")
            type_hint = _text(type_node, source) if type_node else ""
            # Can have multiple identifiers for one type: func(a, b int)
            names = [
                _text(n, source) for n in child.named_children if n.type in ("identifier", "_")
            ]
            if not names:
                # Anonymous parameter: func(int)
                params.append(ParsedParameter(name="", type_hint=type_hint))
            for name in names:
                params.append(ParsedParameter(name=name, type_hint=type_hint))
        elif child.type == "variadic_parameter_declaration":
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
    if node.type in ("type_identifier", "package_identifier"):
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
            if child.type == "package_clause":
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
            if child.type == "function_declaration":
                fn = self._parse_function(child, source)
                if self.include_private or _is_exported(fn.name):
                    module.functions.append(fn)

            elif child.type == "method_declaration":
                fn = self._parse_method(child, source)
                receiver_node = child.child_by_field_name("receiver")
                if receiver_node:
                    tid = _find_type_identifier(receiver_node)
                    if tid:
                        rcv_type = _text(tid, source)
                        if self.include_private or _is_exported(fn.name):
                            methods_by_receiver.setdefault(rcv_type, []).append(fn)

            elif child.type == "type_declaration":
                for spec in child.named_children:
                    if spec.type in ("type_spec", "type_alias"):
                        cls = self._parse_type_spec(spec, source)
                        if self.include_private or _is_exported(cls.name):
                            module.classes.append(cls)

            elif child.type in ("const_declaration", "var_declaration"):
                specs = []
                for sub in child.named_children:
                    if sub.type in ("const_spec", "var_spec"):
                        specs.append(sub)
                    elif sub.type in ("const_spec_list", "var_spec_list"):
                        for spec in sub.named_children:
                            if spec.type in ("const_spec", "var_spec"):
                                specs.append(spec)

                for spec in specs:
                    # const ( a, b = 1, 2 )
                    # tree-sitter-go: const_spec has 'name' (identifiers) and 'type' and 'values'
                    type_node = spec.child_by_field_name("type")
                    type_hint = _text(type_node, source) if type_node else ""

                    # In const_spec/var_spec, identifiers are just children usually,
                    # but some might be field 'name'.
                    names = [n for n in spec.named_children if n.type == "identifier"]
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
            and node.parent.type == "type_declaration"
            and len([c for c in node.parent.named_children if c.type == "type_spec"]) == 1
        ):
            # Try parent if it's a single type decl: type Foo struct {}
            docstring = _get_doc(node.parent, source)

        bases: list[str] = []
        methods: list[ParsedFunction] = []

        if type_node:
            if type_node.type == "struct_type":
                # field_declaration_list is often a child of struct_type, but not necessarily by field name 'fields'
                # in my exploration it was field_declaration_list
                field_list = type_node.child_by_field_name("fields")
                if not field_list:
                    # Fallback to finding by type if field_by_name failed
                    for c in type_node.children:
                        if c.type == "field_declaration_list":
                            field_list = c
                            break

                if field_list:
                    for field in field_list.named_children:
                        if (
                            field.type == "field_declaration"
                            and not field.child_by_field_name("name")
                            and not any(c.type == "field_identifier" for c in field.children)
                        ):
                            # check for anonymous/embedded fields
                            # usually they don't have a name field
                            # If it doesn't have field_identifier, it's likely embedded
                            bases.append(_text(field, source))
            elif type_node.type == "interface_type":
                # In tree-sitter-go, the methods/embedded types are named children of interface_type
                for child in type_node.named_children:
                    if child.type == "type_elem":
                        tid = _find_type_identifier(child)
                        if tid:
                            bases.append(_text(tid, source))
                    elif child.type in ("method_elem", "method_spec"):
                        # Extract as a function
                        fn_name_node = child.child_by_field_name("name")
                        params_node = child.child_by_field_name("parameters")
                        result_node = child.child_by_field_name("result")

                        # Fallback for method_elem which might not have field names set up the same way
                        if not fn_name_node:
                            for c in child.named_children:
                                if c.type == "field_identifier":
                                    fn_name_node = c
                                    break
                        if not params_node:
                            for c in child.named_children:
                                if c.type == "parameter_list":
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
                                    "type_identifier",
                                    "parameter_list",
                                    "qualified_type",
                                    "pointer_type",
                                    "array_type",
                                    "map_type",
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
