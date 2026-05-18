"""Language parsers.

Each parser converts a :class:`~codexa.walker.SourceFile` into a
:class:`~codexa.parsers.base.ParsedModule`.
"""

from __future__ import annotations

from codexa.parsers.base import BaseParser, ParsedClass, ParsedFunction, ParsedModule
from codexa.parsers.python import PythonParser
from codexa.parsers.typescript import TypeScriptParser

__all__ = [
    "BaseParser",
    "ParsedClass",
    "ParsedFunction",
    "ParsedModule",
    "PythonParser",
    "TypeScriptParser",
]


def parser_for(language: str) -> BaseParser | None:
    """Return a parser instance for ``language`` or ``None`` if unsupported."""
    if language == "python":
        return PythonParser()
    if language in ("javascript", "typescript"):
        return TypeScriptParser()
    return None
