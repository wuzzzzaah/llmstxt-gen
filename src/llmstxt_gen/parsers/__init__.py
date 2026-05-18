"""Language parsers.

Each parser converts a :class:`~llmstxt_gen.walker.SourceFile` into a
:class:`~llmstxt_gen.parsers.base.ParsedModule`.
"""

from __future__ import annotations

from llmstxt_gen.parsers.base import BaseParser, ParsedClass, ParsedFunction, ParsedModule
from llmstxt_gen.parsers.go import GoParser
from llmstxt_gen.parsers.python import PythonParser
from llmstxt_gen.parsers.rust import RustParser
from llmstxt_gen.parsers.typescript import TypeScriptParser

__all__ = [
    "BaseParser",
    "ParsedClass",
    "ParsedFunction",
    "ParsedModule",
    "GoParser",
    "PythonParser",
    "RustParser",
    "TypeScriptParser",
]


def parser_for(language: str) -> BaseParser | None:
    """Return a parser instance for ``language`` or ``None`` if unsupported."""
    if language == "python":
        return PythonParser()
    if language in ("javascript", "typescript"):
        return TypeScriptParser()
    if language == "go":
        return GoParser()
    if language == "rust":
        return RustParser()
    return None
