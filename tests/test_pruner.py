from codexa.parsers.base import (
    ParsedClass,
    ParsedConstant,
    ParsedFunction,
    ParsedModule,
    ParsedParameter,
)
from codexa.pruner import estimate_tokens, estimate_total_tokens, prune_modules


def _module(name: str = "m") -> ParsedModule:
    return ParsedModule(
        name=name,
        path=f"{name}.py",
        language="python",
        docstring="A module.",
        functions=[
            ParsedFunction(
                name="f",
                parameters=[ParsedParameter(name="x", type_hint="int", default="0")],
                return_type="int",
                docstring="Do something useful." * 20,
            )
        ],
        classes=[
            ParsedClass(
                name="C",
                docstring="A class.",
                methods=[
                    ParsedFunction(
                        name="m",
                        parameters=[ParsedParameter(name="self")],
                        docstring="Method." * 20,
                    )
                ],
            )
        ],
        constants=[ParsedConstant(name="K", type_hint="int", value="1")],
    )


def test_estimate_tokens_handles_empty_string() -> None:
    assert estimate_tokens("") >= 1


def test_prune_returns_copy_when_under_budget() -> None:
    mods = [_module()]
    pruned = prune_modules(mods, max_tokens=10_000)
    assert pruned is not mods
    assert pruned[0].constants[0].name == "K"


def test_prune_drops_constants_first() -> None:
    mods = [_module()]
    big = estimate_total_tokens(mods)
    pruned = prune_modules(mods, max_tokens=big - 5)
    assert pruned[0].constants == []
    # untouched original
    assert mods[0].constants[0].name == "K"


def test_prune_aggressively_drops_methods_and_docstrings() -> None:
    mods = [_module()]
    pruned = prune_modules(mods, max_tokens=20)
    # class names always preserved
    assert pruned[0].classes[0].name == "C"
    # methods or method docstrings dropped under heavy pressure
    assert pruned[0].classes[0].methods == [] or all(
        m.docstring == "" for m in pruned[0].classes[0].methods
    )
