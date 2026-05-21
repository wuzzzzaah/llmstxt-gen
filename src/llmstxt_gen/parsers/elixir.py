"""Elixir parser backed by tree-sitter.

Extracts module-level docstrings, functions, macros, structs, and constants.
Respects public/private visibility for functions and macros.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_elixir
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

_ELIXIR_LANGUAGE = Language(tree_sitter_elixir.language())

_STRING = "string"
_QUOTED_CONTENT = "quoted_content"
_INTERPOLATION = "interpolation"
_CALL = "call"
_UNARY_OPERATOR = "unary_operator"
_DO_BLOCK = "do_block"
_IDENTIFIER = "identifier"
_BINARY_OPERATOR = "binary_operator"


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_string_content(node: Node, source: bytes) -> str:
    """Extract content from a string or heredoc."""
    if node.type == _STRING:
        # Usually it has children like " (quoted_content) "
        content = []
        for child in node.children:
            if child.type == _QUOTED_CONTENT or child.type == _INTERPOLATION:
                content.append(_text(child, source))
        return "".join(content)
    return _text(node, source).strip("\"'")


class ElixirParser(BaseParser):
    """Parse Elixir source via tree-sitter."""

    language = "elixir"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_ELIXIR_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="elixir",
        )

        self._parse_nodes(root, source, module.functions, module.classes, module.constants, module)

        return module

    def _parse_nodes(
        self,
        node: Node,
        source: bytes,
        functions: list[ParsedFunction],
        classes: list[ParsedClass],
        constants: list[ParsedConstant],
        module: ParsedModule,
    ) -> None:
        last_doc = ""
        last_spec_params: list[ParsedParameter] | None = None

        for child in node.named_children:
            if child.type == _CALL:
                target = child.child_by_field_name("target")
                if not target and child.named_child_count > 0:
                    target = child.named_children[0]

                if not target:
                    continue

                target_text = _text(target, source)

                if target_text in ("alias", "import", "require", "use"):
                    args = child.child_by_field_name("arguments")
                    if args:
                        # Extract the first argument as the import path/module
                        module.imports.append(_text(args.named_children[0], source))

                if target_text in ("defmodule", "defprotocol", "defimpl"):
                    cls = self._parse_module_like(child, source, module)
                    if cls:
                        classes.append(cls)
                    last_doc = ""
                    last_spec_params = None

                elif target_text in ("def", "defmacro", "defp", "defmacrop"):
                    is_private = target_text in ("defp", "defmacrop")
                    if self.include_private or not is_private:
                        fn = self._parse_function(
                            child, source, is_private, last_doc, last_spec_params
                        )
                        if fn:
                            existing = next((f for f in functions if f.name == fn.name), None)
                            if existing:
                                existing._heads_count += 1
                            else:
                                functions.append(fn)
                    last_doc = ""
                    last_spec_params = None

            elif child.type == _UNARY_OPERATOR:
                if len(child.children) >= 2 and _text(child.children[0], source) == "@":
                    inner_call = child.children[1]
                    if inner_call.type == _CALL:
                        attr_name_node = inner_call.child_by_field_name("target")
                        if not attr_name_node and inner_call.named_child_count > 0:
                            attr_name_node = inner_call.named_children[0]
                        attr_name = _text(attr_name_node, source) if attr_name_node else ""
                        attr_args = inner_call.child_by_field_name("arguments")
                        if not attr_args and inner_call.named_child_count > 1:
                            attr_args = inner_call.named_children[1]

                        if attr_name == "doc" and attr_args:
                            last_doc = _get_string_content(attr_args.named_children[0], source)
                        elif attr_name == "spec" and attr_args:
                            last_spec_params = self._parse_spec(attr_args, source)
                        elif attr_name not in ("moduledoc", "behaviour") and attr_args:
                            constants.append(
                                ParsedConstant(name=attr_name, value=_text(attr_args, source))
                            )

        for fn in functions:
            if fn._heads_count > 1:
                fn.name = f"{fn.name} (+{fn._heads_count - 1} heads)"

    def _parse_module_like(
        self, node: Node, source: bytes, module: ParsedModule
    ) -> ParsedClass | None:
        args = node.child_by_field_name("arguments")
        if not args and node.named_child_count > 1:
            args = node.named_children[1]

        if not args or args.named_child_count < 1:
            return None

        # For defimpl, name might be multiple args
        name = _text(args.named_children[0], source)
        if _text(node.named_children[0], source) == "defimpl" and args.named_child_count > 1:
            # Join args for name, e.g. SampleProtocol, for: Integer
            name = _text(args, source)

        docstring = ""
        bases: list[str] = []
        methods: list[ParsedFunction] = []
        class_vars: list[ParsedConstant] = []

        do_block = None
        for child in node.children:
            if child.type == _DO_BLOCK:
                do_block = child
                break

        if do_block:
            last_doc = ""
            last_spec_params = None

            for child in do_block.children:
                if child.type == _CALL:
                    target = child.child_by_field_name("target")
                    if not target and child.named_child_count > 0:
                        target = child.named_children[0]
                    if not target:
                        continue
                    target_text = _text(target, source)

                    if target_text in ("alias", "import", "require", "use"):
                        args = child.child_by_field_name("arguments")
                        if args:
                            module.imports.append(_text(args.named_children[0], source))

                    if target_text in ("def", "defmacro", "defp", "defmacrop"):
                        is_private = target_text in ("defp", "defmacrop")
                        if self.include_private or not is_private:
                            fn = self._parse_function(
                                child, source, is_private, last_doc, last_spec_params
                            )
                            if fn:
                                existing = next((f for f in methods if f.name == fn.name), None)
                                if existing:
                                    existing._heads_count += 1
                                else:
                                    methods.append(fn)
                        last_doc = ""
                        last_spec_params = None
                    elif target_text == "defstruct":
                        struct_args = child.child_by_field_name("arguments")
                        if not struct_args and child.named_child_count > 1:
                            struct_args = child.named_children[1]
                        if struct_args:
                            class_vars.append(
                                ParsedConstant(name="struct", value=_text(struct_args, source))
                            )
                elif child.type == _UNARY_OPERATOR:
                    if len(child.children) >= 2 and _text(child.children[0], source) == "@":
                        inner_call = child.children[1]
                        if inner_call.type == _CALL:
                            attr_name_node = inner_call.child_by_field_name("target")
                            if not attr_name_node and inner_call.named_child_count > 0:
                                attr_name_node = inner_call.named_children[0]
                            attr_name = _text(attr_name_node, source) if attr_name_node else ""
                            attr_args = inner_call.child_by_field_name("arguments")
                            if not attr_args and inner_call.named_child_count > 1:
                                attr_args = inner_call.named_children[1]

                            if attr_name == "moduledoc" and attr_args:
                                docstring = _get_string_content(attr_args.named_children[0], source)
                            elif attr_name == "behaviour" and attr_args:
                                bases.append(_text(attr_args.named_children[0], source))
                            elif attr_name == "doc" and attr_args:
                                last_doc = _get_string_content(attr_args.named_children[0], source)
                            elif attr_name == "spec" and attr_args:
                                last_spec_params = self._parse_spec(attr_args, source)
                            elif attr_name not in ("moduledoc", "behaviour") and attr_args:
                                class_vars.append(
                                    ParsedConstant(
                                        name=attr_name, value=_text(attr_args, source)
                                    )
                                )

            for fn in methods:
                if fn._heads_count > 1:
                    fn.name = f"{fn.name} (+{fn._heads_count - 1} heads)"

        return ParsedClass(
            name=name,
            docstring=docstring,
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )

    def _parse_function(
        self,
        node: Node,
        source: bytes,
        is_private: bool,
        docstring: str,
        spec_params: list[ParsedParameter] | None,
    ) -> ParsedFunction | None:
        args_node = node.child_by_field_name("arguments")
        if not args_node and node.named_child_count > 1:
            args_node = node.named_children[1]

        if not args_node:
            return None

        fn_call = args_node.named_children[0]
        if fn_call.type != _CALL and fn_call.type != _IDENTIFIER:
            return None

        if fn_call.type == _CALL:
            name_node = fn_call.child_by_field_name("target")
            if not name_node and fn_call.named_child_count > 0:
                name_node = fn_call.named_children[0]
            name = _text(name_node, source) if name_node else ""

            params = []
            if spec_params:
                params = spec_params
            else:
                fn_args = fn_call.child_by_field_name("arguments")
                if not fn_args and fn_call.named_child_count > 1:
                    fn_args = fn_call.named_children[1]
                if fn_args:
                    for arg in fn_args.named_children:
                        params.append(ParsedParameter(name=_text(arg, source)))
        else:
            name = _text(fn_call, source)
            params = []

        return ParsedFunction(
            name=name,
            parameters=params,
            docstring=docstring,
            is_private=is_private,
            line=node.start_point[0] + 1,
        )

    def _parse_spec(self, node: Node, source: bytes) -> list[ParsedParameter]:
        if node.named_child_count == 0:
            return []

        op = node.named_children[0]
        if op.type == _BINARY_OPERATOR:
            left = op.named_children[0]
            if left.type == _CALL:
                fn_args = left.child_by_field_name("arguments")
                if not fn_args and left.named_child_count > 1:
                    fn_args = left.named_children[1]
                if fn_args:
                    params = []
                    for arg in fn_args.named_children:
                        params.append(ParsedParameter(name="", type_hint=_text(arg, source)))
                    return params
        return []
