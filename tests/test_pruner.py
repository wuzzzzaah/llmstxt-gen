import logging

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.parsers.base import (
    ParsedClass,
    ParsedConstant,
    ParsedFunction,
    ParsedModule,
    ParsedParameter,
)
from llmstxt_gen.pruner import estimate_tokens, prune_modules

logger = logging.getLogger(__name__)


def _render_mock(modules: list[ParsedModule], config: LlmsTxtConfig) -> str:
    """A simple mock renderer for testing pruning stages."""
    lines = []
    for m in modules:
        lines.append(f"Module: {m.path}")
        if m.docstring:
            lines.append(f"Doc: {m.docstring}")
        for fn in m.functions:
            lines.append(f"Func: {fn.name}")
            if fn.docstring:
                lines.append(f"FuncDoc: {fn.docstring}")
        for cls in m.classes:
            lines.append(f"Class: {cls.name}")
            if cls.docstring:
                lines.append(f"ClassDoc: {cls.docstring}")
            for method in cls.methods:
                lines.append(f"Method: {method.name}")
                if method.docstring:
                    lines.append(f"MethodDoc: {method.docstring}")
            for cv in cls.class_vars:
                lines.append(f"ClassVar: {cv.name}")
        for const in m.constants:
            lines.append(f"Const: {const.name}")
    return "\n".join(lines)


def _module(name: str = "m") -> ParsedModule:
    return ParsedModule(
        name=name,
        path=f"{name}.py",
        language="python",
        docstring="First sentence. Second sentence.",
        functions=[
            ParsedFunction(
                name="f",
                parameters=[ParsedParameter(name="x", type_hint="int", default="0")],
                return_type="int",
                docstring="Func first. Func second.",
                is_private=False,
            ),
            ParsedFunction(
                name="_priv_f",
                docstring="Private func.",
                is_private=True,
            )
        ],
        classes=[
            ParsedClass(
                name="C",
                docstring="Class first. Class second.",
                methods=[
                    ParsedFunction(
                        name="m",
                        parameters=[ParsedParameter(name="self")],
                        docstring="Method first. Method second.",
                        is_private=False,
                    ),
                    ParsedFunction(
                        name="_priv_m",
                        docstring="Private method.",
                        is_private=True,
                    )
                ],
                class_vars=[ParsedConstant(name="CV", value="1")]
            )
        ],
        constants=[ParsedConstant(name="K", type_hint="int", value="1")],
    )


def test_estimate_tokens_handles_empty_string() -> None:
    assert estimate_tokens("") >= 1


def test_prune_returns_copy_when_under_budget() -> None:
    config = LlmsTxtConfig()
    mods = [_module()]
    # High budget, no pruning
    pruned = prune_modules(mods, config, max_tokens=10_000, render_fn=_render_mock)
    assert pruned is not mods
    assert len(pruned[0].constants) == 1
    assert "Second sentence" in pruned[0].docstring


def test_prune_stage1_truncates_docstrings() -> None:
    config = LlmsTxtConfig()
    mods = [_module()]
    # Set budget just below what's needed for full docstrings
    full_text = _render_mock(mods, config)
    full_tokens = estimate_tokens(full_text)

    pruned = prune_modules(mods, config, max_tokens=full_tokens - 1, render_fn=_render_mock)

    assert pruned[0].docstring == "First sentence."
    assert pruned[0].functions[0].docstring == "Func first."
    assert pruned[0].classes[0].docstring == "Class first."
    assert pruned[0].classes[0].methods[0].docstring == "Method first."
    # Constants should still be there if stage 1 was enough
    assert len(pruned[0].constants) == 1


def test_prune_stage2_drops_constants() -> None:
    config = LlmsTxtConfig()
    mods = [_module()]
    # Truncate docstrings manually to see what Stage 1 would result in
    m1 = _module()
    m1.docstring = "First sentence."
    m1.functions[0].docstring = "Func first."
    m1.classes[0].docstring = "Class first."
    m1.classes[0].methods[0].docstring = "Method first."

    stage1_tokens = estimate_tokens(_render_mock([m1], config))

    pruned = prune_modules(mods, config, max_tokens=stage1_tokens - 1, render_fn=_render_mock)

    assert len(pruned[0].constants) == 0
    assert len(pruned[0].classes[0].class_vars) == 0
    # Docstrings should also be truncated
    assert pruned[0].docstring == "First sentence."


def test_prune_stage3_drops_private() -> None:
    config = LlmsTxtConfig()
    mods = [_module()]

    m2 = _module()
    # Apply Stage 1 & 2
    m2.docstring = "First sentence."
    m2.functions[0].docstring = "Func first."
    m2.classes[0].docstring = "Class first."
    m2.classes[0].methods[0].docstring = "Method first."
    m2.constants = []
    m2.classes[0].class_vars = []

    stage2_tokens = estimate_tokens(_render_mock([m2], config))

    pruned = prune_modules(mods, config, max_tokens=stage2_tokens - 1, render_fn=_render_mock)

    # Private functions and methods should be gone
    assert len(pruned[0].functions) == 1
    assert pruned[0].functions[0].name == "f"
    assert len(pruned[0].classes[0].methods) == 1
    assert pruned[0].classes[0].methods[0].name == "m"


def test_prune_stage4_drops_modules() -> None:
    config = LlmsTxtConfig()
    # Create two modules, one referencing the other's name in docstring
    m_ref = _module("referenced")
    m_other = _module("other")
    m_other.docstring = "I refer to referenced here."

    mods = [m_ref, m_other]

    # Target a budget that is enough for one module but not both
    # One module rendered by _render_mock is roughly 15-20 tokens
    # But wait, my Stage 1-3 also apply.
    # After stage 1-3, each module in _render_mock is very small.
    # Module: referenced.py (3 tokens)
    # Func: f (2 tokens)
    # FuncDoc: Func first. (3 tokens)
    # Class: C (1 token)
    # ClassDoc: Class first. (3 tokens)
    # Method: m (1 token)
    # MethodDoc: Method first. (3 tokens)
    # Total ~ 16 tokens per module.
    # 25 tokens should keep one.

    full_text = _render_mock(mods, config)
    logger.info("Full text tokens: %d", estimate_tokens(full_text))

    pruned = prune_modules(mods, config, max_tokens=50, render_fn=_render_mock)

    # "other" should be dropped first because "referenced" is referenced by it
    assert len(pruned) == 1
    assert pruned[0].name == "referenced"


def test_prune_logs_warnings(caplog) -> None:
    config = LlmsTxtConfig()
    mods = [_module()]
    with caplog.at_level(logging.WARNING):
        prune_modules(mods, config, max_tokens=10, render_fn=_render_mock)

    assert "truncated" in caplog.text
    assert "dropped" in caplog.text
