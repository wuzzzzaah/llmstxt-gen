"""Language parsers.

Each parser converts a :class:`~llmstxt_gen.walker.SourceFile` into a
:class:`~llmstxt_gen.parsers.base.ParsedModule`.
"""

from __future__ import annotations

from llmstxt_gen.parsers.base import BaseParser, ParsedClass, ParsedFunction, ParsedModule
from llmstxt_gen.parsers.cpp import CppParser
from llmstxt_gen.parsers.scala import ScalaParser
from llmstxt_gen.parsers.csharp import CSharpParser
from llmstxt_gen.parsers.go import GoParser
from llmstxt_gen.parsers.java import JavaParser
from llmstxt_gen.parsers.python import PythonParser
from llmstxt_gen.parsers.ruby import RubyParser
from llmstxt_gen.parsers.rust import RustParser
from llmstxt_gen.parsers.typescript import TypeScriptParser

__all__ = [
    "BaseParser",
    "ParsedClass",
    "ParsedFunction",
    "ParsedModule",
    "CppParser",
    "CSharpParser",
    "GoParser",
    "JavaParser",
    "PythonParser",
    "RubyParser",
    "RustParser",
    "TypeScriptParser",
    "ScalaParser",
]


def parser_for(language: str) -> BaseParser | None:
    """Return a parser instance for ``language`` or ``None`` if unsupported."""
    if language == "python":
        return PythonParser()
    if language in ("javascript", "typescript"):
        return TypeScriptParser()
    if language == "go":
        return GoParser()
    if language == "java":
        return JavaParser()
    if language == "ruby":
        return RubyParser()
    if language == "csharp":
        return CSharpParser()
    if language == "rust":
        return RustParser()
    if language in ("c", "cpp"):
        return CppParser()
    if language == "scala":
        return ScalaParser()
    return None
