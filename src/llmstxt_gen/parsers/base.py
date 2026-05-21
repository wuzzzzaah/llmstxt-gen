"""Abstract base parser and shared data models.

All language parsers produce instances of :class:`ParsedModule`. Downstream
stages (pruner, renderer) work exclusively against these structures, which is
what lets llmstxt-gen stay language-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from llmstxt_gen.walker import SourceFile


@dataclass
class ParsedParameter:
    """A function or method parameter."""

    name: str
    type_hint: str = ""
    default: str = ""
    is_optional: bool = False


@dataclass
class ParsedFunction:
    """A function, method, or arrow function definition."""

    name: str
    parameters: list[ParsedParameter] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    line: int = 0
    is_async: bool = False
    is_private: bool = False
    is_property: bool = False
    decorators: list[str] = field(default_factory=list)
    _heads_count: int = 1


@dataclass
class ParsedConstant:
    """A module-level constant with a known type annotation."""

    name: str
    type_hint: str = ""
    value: str = ""


@dataclass
class ParsedClass:
    """A class definition with its methods and class variables."""

    name: str
    docstring: str = ""
    bases: list[str] = field(default_factory=list)
    methods: list[ParsedFunction] = field(default_factory=list)
    class_vars: list[ParsedConstant] = field(default_factory=list)
    line: int = 0


@dataclass
class ParsedRoute:
    """An HTTP route handler (Express, Next.js, etc.)."""

    method: str
    path: str
    handler: str = ""
    line: int = 0
    docstring: str = ""


@dataclass
class ParsedModule:
    """A single source file converted to a structured representation."""

    name: str
    path: str
    language: str
    docstring: str = ""
    functions: list[ParsedFunction] = field(default_factory=list)
    classes: list[ParsedClass] = field(default_factory=list)
    constants: list[ParsedConstant] = field(default_factory=list)
    routes: list[ParsedRoute] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    env_vars: dict[str, list[str]] = field(default_factory=dict)


def clean_docstring(raw: str) -> str:
    """Clean a docstring by removing comment markers and normalizing whitespace.

    Handles:
    - Javadoc/JSDoc/Doxygen: /** ... */
    - Block comments: /* ... */
    - Triple-slash: /// ... or //! ...
    - Double-slash: // ...
    - Hash: # ...

    Leading asterisks on each line are also removed.
    """
    if not raw:
        return ""

    raw = raw.strip()

    # Handle block comments markers at start/end
    if raw.startswith("/**"):
        raw = raw[3:]
    elif raw.startswith("/*"):
        raw = raw[2:]

    if raw.endswith("*/"):
        raw = raw[:-2]

    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        line = line.strip()
        # Remove common comment markers
        if line.startswith("///") or line.startswith("//!"):
            line = line[3:]
        elif line.startswith("//"):
            line = line[2:]
        elif line.startswith("#"):
            line = line[1:]
        elif line.startswith("*"):
            line = line.lstrip("*")

        cleaned.append(line.strip())

    return "\n".join(cleaned).strip()


class BaseParser(ABC):
    """Abstract parser interface implemented by every language backend."""

    language: str = ""

    @abstractmethod
    def parse(self, source_file: SourceFile) -> ParsedModule:
        """Parse ``source_file`` into a :class:`ParsedModule`."""
        raise NotImplementedError
