from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.parsers.base import ParsedClass, ParsedFunction, ParsedModule, ParsedParameter
from llmstxt_gen.renderer import render_full, render_summary


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
    cfg = LlmsTxtConfig(name="demo", description="A demo project.")
    out = render_summary(_modules(), cfg)
    assert out.startswith("# demo")
    assert "> A demo project." in out
    assert "## Modules" in out
    # Keys are path-based (without extension), not bare filenames
    assert "[src/calc](llms-full.txt#" in out


def test_render_summary_uses_path_key_not_name() -> None:
    """Path-based keys disambiguate files that share a name (e.g. Next.js page.tsx)."""
    modules = [
        ParsedModule(
            name="page",
            path="app/analytics/page.tsx",
            language="typescript",
            docstring="Analytics page.",
        ),
        ParsedModule(
            name="page",
            path="app/journeys/page.tsx",
            language="typescript",
            docstring="Journeys page.",
        ),
    ]
    cfg = LlmsTxtConfig(name="demo")
    out = render_summary(modules, cfg)
    assert "[app/analytics/page]" in out
    assert "[app/journeys/page]" in out
    # Bare name must not appear as a link key
    assert "[page]" not in out


def test_render_full_emits_signatures_and_classes() -> None:
    cfg = LlmsTxtConfig(name="demo")
    out = render_full(_modules(), cfg)
    assert "## src/calc.py" in out
    assert "`add(a: int, b: int = 0) -> int`" in out
    assert "`Calc(object)`" in out
    assert "`inc(self) -> None`" in out


def test_render_full_handles_zod_constants() -> None:
    from llmstxt_gen.parsers.base import ParsedConstant

    module = ParsedModule(
        name="schemas",
        path="src/schemas.ts",
        language="typescript",
        constants=[
            ParsedConstant(
                name="createJourneySchema",
                type_hint="{ title: string, description?: string }",
                value="z.object({ ... })",
            ),
            ParsedConstant(
                name="updateJourneySchema",
                value="createJourneySchema.partial()",
            ),
            ParsedConstant(
                name="simpleSchema",
                value="z.string()",
            ),
            ParsedConstant(
                name="complexSchema",
                value="z.object({ " + "a: z.string()," * 50 + " })",
            ),
        ],
    )
    cfg = LlmsTxtConfig(name="test")
    out = render_full([module], cfg)

    # Uses type_hint if available
    assert "- `createJourneySchema`: `{ title: string, description?: string }`" in out
    # Falls back to value if it looks like Zod
    assert "- `updateJourneySchema`: `createJourneySchema.partial()`" in out
    assert "- `simpleSchema`: `z.string()`" in out
    # Truncates long values
    assert "..." in out
    assert len(next(line for line in out.splitlines() if "complexSchema" in line)) < 150
