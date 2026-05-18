from codexa.config import CodexaConfig
from codexa.parsers.base import ParsedClass, ParsedFunction, ParsedModule, ParsedParameter
from codexa.renderer import render_full, render_summary


def _modules() -> list[ParsedModule]:
    return [
        ParsedModule(
            name="calc",
            path="src/calc.py",
            language="python",
            docstring="Adds numbers.",
            functions=[
                ParsedFunction(
                    name="add",
                    parameters=[
                        ParsedParameter(name="a", type_hint="int"),
                        ParsedParameter(name="b", type_hint="int", default="0"),
                    ],
                    return_type="int",
                    docstring="Return a + b.",
                )
            ],
            classes=[
                ParsedClass(
                    name="Calc",
                    docstring="A calculator.",
                    bases=["object"],
                    methods=[
                        ParsedFunction(
                            name="inc",
                            parameters=[ParsedParameter(name="self")],
                            return_type="None",
                        )
                    ],
                )
            ],
        )
    ]


def test_render_summary_includes_project_header_and_modules() -> None:
    cfg = CodexaConfig(name="demo", description="A demo project.")
    out = render_summary(_modules(), cfg)
    assert out.startswith("# demo")
    assert "> A demo project." in out
    assert "calc:" in out
    assert "## Modules" in out
    assert "[calc](llms-full.txt#" in out


def test_render_full_emits_signatures_and_classes() -> None:
    cfg = CodexaConfig(name="demo")
    out = render_full(_modules(), cfg)
    assert "## src/calc.py" in out
    assert "`add(a: int, b: int = 0) -> int`" in out
    assert "`Calc(object)`" in out
    assert "`inc(self) -> None`" in out
