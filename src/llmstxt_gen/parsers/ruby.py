"""Ruby parser backed by tree-sitter.

Extracts module-level comments, top-level methods, classes, modules, and
constants. Expands attr_* macros into method definitions. Respects
private/protected visibility.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_ruby
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

_RUBY_LANGUAGE = Language(tree_sitter_ruby.language())


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _get_doc(node: Node, source: bytes) -> str:
    docs: list[str] = []
    curr = node.prev_sibling
    # Ruby comments are often separate nodes preceding the definition
    while curr and curr.type in ("comment", "line_break"):
        if curr.type == "comment":
            text = _text(curr, source).strip()
            if text.startswith("#"):
                docs.insert(0, text[1:].strip())
        curr = curr.prev_sibling
    return "\n".join(docs).strip()


def _parse_parameters(params_node: Node | None, source: bytes) -> list[ParsedParameter]:
    if params_node is None:
        return []
    params: list[ParsedParameter] = []
    # params_node is often (method_parameters)
    for child in params_node.named_children:
        if child.type == "identifier":
            params.append(ParsedParameter(name=_text(child, source)))
        elif child.type == "optional_parameter":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            params.append(
                ParsedParameter(
                    name=_text(name_node, source) if name_node else "",
                    default=_text(value_node, source) if value_node else "",
                )
            )
        elif child.type == "splat_parameter":
            name_node = child.named_children[0] if child.named_children else None
            name = _text(name_node, source) if name_node else ""
            params.append(ParsedParameter(name=f"*{name}"))
        elif child.type == "hash_splat_parameter":
            name_node = child.named_children[0] if child.named_children else None
            name = _text(name_node, source) if name_node else ""
            params.append(ParsedParameter(name=f"**{name}"))
        elif child.type == "block_parameter":
            name_node = child.named_children[0] if child.named_children else None
            name = _text(name_node, source) if name_node else ""
            params.append(ParsedParameter(name=f"&{name}"))
        elif child.type == "keyword_parameter":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            params.append(
                ParsedParameter(
                    name=f"{_text(name_node, source)}:" if name_node else "",
                    default=_text(value_node, source) if value_node else "",
                )
            )
    return params


class RubyParser(BaseParser):
    """Parse Ruby source via tree-sitter."""

    language = "ruby"

    def __init__(self, include_private: bool = False) -> None:
        self.include_private = include_private
        self._parser: Any = Parser(_RUBY_LANGUAGE)

    def parse(self, source_file: SourceFile) -> ParsedModule:
        source = source_file.content.encode("utf-8")
        tree = self._parser.parse(source)
        root = tree.root_node

        module = ParsedModule(
            name=source_file.path.stem,
            path=str(source_file.path),
            language="ruby",
        )

        self._parse_body(root, source, module.functions, module.classes, module.constants)

        return module

    def _parse_body(
        self,
        node: Node,
        source: bytes,
        functions: list[ParsedFunction],
        classes: list[ParsedClass],
        constants: list[ParsedConstant],
    ) -> None:
        # Visibility state for current scope
        current_visibility = "public"

        # Body might be the root or a body_statement
        target_nodes = node.named_children
        if node.type == "body_statement":
            target_nodes = node.named_children

        for child in target_nodes:
            if child.type == "method":
                fn = self._parse_method(child, source, current_visibility)
                if self.include_private or not fn.is_private:
                    functions.append(fn)

            elif child.type in ("class", "module"):
                cls = self._parse_class_or_module(child, source)
                classes.append(cls)

            elif child.type == "assignment":
                left = child.child_by_field_name("left")
                right = child.child_by_field_name("right")
                if left and left.type == "constant":
                    constants.append(
                        ParsedConstant(
                            name=_text(left, source),
                            value=_text(right, source) if right else "",
                        )
                    )

            elif child.type == "identifier":
                val = _text(child, source)
                if val in ("private", "protected", "public"):
                    current_visibility = val

            elif child.type == "call":
                method_name_node = child.child_by_field_name("method")
                method_name = _text(method_name_node, source) if method_name_node else ""

                if method_name in ("private", "protected", "public"):
                    # Check if it's a standalone call (sets visibility)
                    # or a modifier: private :foo or private def foo
                    args = child.child_by_field_name("arguments")
                    if not args:
                        current_visibility = method_name
                    else:
                        # Modifier use: we don't easily track which methods are affected
                        # without more complex logic. For now, let's handle the common case.
                        # If it's a method definition as an argument:
                        for arg in args.named_children:
                            if arg.type == "method":
                                fn = self._parse_method(arg, source, method_name)
                                if self.include_private or not fn.is_private:
                                    functions.append(fn)
                elif method_name in ("attr_accessor", "attr_reader", "attr_writer"):
                    args = child.child_by_field_name("arguments")
                    if args:
                        docstring = _get_doc(child, source)
                        for arg in args.named_children:
                            if arg.type in ("simple_symbol", "string"):
                                name = _text(arg, source).lstrip(":")
                                if arg.type == "string":
                                    name = name.strip("'\"")

                                is_private = current_visibility != "public"

                                if method_name in (
                                    "attr_reader",
                                    "attr_accessor",
                                ) and (self.include_private or not is_private):
                                    functions.append(
                                        ParsedFunction(
                                            name=name,
                                            docstring=docstring,
                                            is_private=is_private,
                                            line=child.start_point[0] + 1,
                                        )
                                    )
                                if method_name in (
                                    "attr_writer",
                                    "attr_accessor",
                                ) and (self.include_private or not is_private):
                                    functions.append(
                                        ParsedFunction(
                                            name=f"{name}=",
                                            parameters=[ParsedParameter(name="value")],
                                            docstring=docstring,
                                            is_private=is_private,
                                            line=child.start_point[0] + 1,
                                        )
                                    )
                elif method_name in ("include", "extend", "prepend"):
                    # These might be handled in _parse_class_or_module if it recurses
                    # But if we are already in a class, we might want to collect them.
                    pass

            # Handle body_statement which can wrap children
            if child.type == "body_statement":
                self._parse_body(child, source, functions, classes, constants)

    def _parse_method(self, node: Node, source: bytes, visibility: str) -> ParsedFunction:
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name = _text(name_node, source) if name_node else ""
        return ParsedFunction(
            name=name,
            parameters=_parse_parameters(params_node, source),
            docstring=_get_doc(node, source),
            line=node.start_point[0] + 1,
            is_private=visibility != "public",
        )

    def _parse_class_or_module(self, node: Node, source: bytes) -> ParsedClass:
        name_node = node.child_by_field_name("name")
        name = _text(name_node, source) if name_node else ""

        bases: list[str] = []
        if node.type == "class":
            superclass_node = node.child_by_field_name("superclass")
            if superclass_node:
                # superclass node is usually '< BaseClass' or '< Scoped::BaseClass'
                # We want the actual type expression after '<'
                # superclass_node in tree-sitter-ruby often has the '<' as a child
                # and then the constant or scope_resolution
                for c in superclass_node.named_children:
                    if c.type in ("constant", "scope_resolution"):
                        bases.append(_text(c, source))

        methods: list[ParsedFunction] = []
        class_vars: list[ParsedConstant] = []

        # We need to collect include/extend/prepend as bases too
        body = node.child_by_field_name("body")
        if body:
            # We'll do a custom pass for this body to extract bases from calls
            for child in body.named_children:
                if child.type == "call":
                    m_name_node = child.child_by_field_name("method")
                    m_name = _text(m_name_node, source) if m_name_node else ""
                    if m_name in ("include", "extend", "prepend"):
                        args = child.child_by_field_name("arguments")
                        if args:
                            for arg in args.named_children:
                                bases.append(f"{m_name}({_text(arg, source)})")

            # Now parse the rest of the body
            temp_classes: list[
                ParsedClass
            ] = []  # Ruby doesn't usually nest classes in a way we want to flatten here?
            # Actually we should probably just recurse and attach them somewhere.
            # Base classes/modules can have nested ones.
            self._parse_body(body, source, methods, temp_classes, class_vars)
            # For now, let's ignore nested classes in llms.txt or decide how to handle them.
            # Python parser omits them from the top level but includes them if they are in a class?
            # Actually Python parser doesn't seem to handle nested classes fully yet based on my quick read.

        return ParsedClass(
            name=name,
            docstring=_get_doc(node, source),
            bases=bases,
            methods=methods,
            class_vars=class_vars,
            line=node.start_point[0] + 1,
        )
