"""llmstxt-gen: AST-aware llms.txt generator.

Public API re-exports the most commonly used entry points so that users can
build their own pipelines on top of the library.
"""

from llmstxt_gen.config import LlmsTxtConfig, load_config
from llmstxt_gen.parsers.base import ParsedClass, ParsedFunction, ParsedModule, ParsedParameter
from llmstxt_gen.pruner import prune_modules
from llmstxt_gen.renderer import render_full, render_summary
from llmstxt_gen.walker import SourceFile, walk_repository
from llmstxt_gen.writer import write_outputs

__version__ = "0.2.0"

__all__ = [
    "LlmsTxtConfig",
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
