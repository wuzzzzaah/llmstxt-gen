"""codexa: AST-aware llms.txt generator.

Public API re-exports the most commonly used entry points so that users can
build their own pipelines on top of the library.
"""

from codexa.config import CodexaConfig, load_config
from codexa.parsers.base import ParsedClass, ParsedFunction, ParsedModule, ParsedParameter
from codexa.pruner import prune_modules
from codexa.renderer import render_full, render_summary
from codexa.walker import SourceFile, walk_repository
from codexa.writer import write_outputs

__version__ = "0.1.0"

__all__ = [
    "CodexaConfig",
    "ParsedClass",
    "ParsedFunction",
    "ParsedModule",
    "ParsedParameter",
    "SourceFile",
    "load_config",
    "prune_modules",
    "render_full",
    "render_summary",
    "walk_repository",
    "write_outputs",
]
