from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.parsers.base import (
    ParsedClass,
    ParsedFunction,
    ParsedModule,
    ParsedParameter,
    ParsedRoute,
)
from llmstxt_gen.renderer import render_full, render_mini, render_summary


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


def test_render_mini_emits_only_signatures() -> None:
    modules = _modules()
    # Add a route and a constant to ensure they are NOT in the mini output
    modules[0].routes = [ParsedRoute(method="GET", path="/test")]
    from llmstxt_gen.parsers.base import ParsedConstant

    modules[0].constants = [ParsedConstant(name="VERSION", value="1.0")]

    cfg = LlmsTxtConfig(name="demo")
    out = render_mini(modules, cfg)

    # Project name and path
    assert out.startswith("demo\nsrc/calc.py")
    # Function signature
    assert "add(a: int, b: int = 0) -> int" in out
    # Class name
    assert "Calc" in out
    # Method signature
    assert "inc(self) -> None" in out

    # No docstrings
    assert "Adds numbers." not in out
    assert "Return a + b." not in out
    assert "A calculator." not in out

    # No constants or routes
    assert "VERSION" not in out
    assert "GET /test" not in out


def test_render_full_includes_env_vars_table() -> None:
    modules = [
        ParsedModule(
            name="a",
            path="src/a.ts",
            language="typescript",
            env_vars={"SUPABASE_URL": ["src/a.ts"], "API_KEY": ["src/a.ts"]},
        ),
        ParsedModule(
            name="b",
            path="src/b.py",
            language="python",
            env_vars={"SUPABASE_URL": ["src/b.py"], "DB_URL": ["src/b.py"]},
        ),
    ]
    cfg = LlmsTxtConfig(name="test")
    out = render_full(modules, cfg)

    assert "## Environment Variables" in out
    assert "| Variable | Files |" in out
    assert "| `SUPABASE_URL` | `src/a.ts`, `src/b.py` |" in out
    assert "| `API_KEY` | `src/a.ts` |" in out
    assert "| `DB_URL` | `src/b.py` |" in out


def test_render_summary_nextjs_heuristic() -> None:
    from llmstxt_gen.parsers.base import ParsedRoute
    module = ParsedModule(
        name="page",
        path="app/dashboard/page.tsx",
        language="typescript",
        routes=[ParsedRoute(method="GET", path="/dashboard", handler="default")],
    )
    cfg = LlmsTxtConfig()
    out = render_summary([module], cfg)
    assert ": Page component at /dashboard." in out


def test_render_summary_routes_heuristic() -> None:
    from llmstxt_gen.parsers.base import ParsedRoute
    module = ParsedModule(
        name="api",
        path="src/api.py",
        language="python",
        routes=[ParsedRoute(method="POST", path="/login", handler="login")],
    )
    cfg = LlmsTxtConfig()
    out = render_summary([module], cfg)
    assert ": Defines HTTP routes." in out


def test_render_summary_filename_heuristic() -> None:
    module = ParsedModule(
        name="utils",
        path="src/utils.py",
        language="python",
        functions=[ParsedFunction(name="helper")],
    )
    cfg = LlmsTxtConfig()
    out = render_summary([module], cfg)
    assert ": Utility functions." in out


def test_render_summary_exported_docstring_heuristic() -> None:
    module = ParsedModule(
        name="logic",
        path="src/logic.py",
        language="python",
        functions=[ParsedFunction(name="do_work", docstring="Does heavy work.")],
    )
    cfg = LlmsTxtConfig()
    out = render_summary([module], cfg)
    assert ": Does heavy work." in out


def test_render_summary_all_heuristic() -> None:
    from llmstxt_gen.parsers.base import ParsedConstant
    module = ParsedModule(
        name="api",
        path="src/api.py",
        language="python",
        constants=[ParsedConstant(name="__all__", value="['Login', 'Logout']")],
    )
    cfg = LlmsTxtConfig()
    out = render_summary([module], cfg)
    assert ": Provides Login, Logout." in out


def test_render_summary_smart_summaries_disabled() -> None:
    module = ParsedModule(
        name="utils",
        path="src/utils.py",
        language="python",
        functions=[ParsedFunction(name="helper")],
    )
    cfg = LlmsTxtConfig(smart_summaries=False)
    out = render_summary([module], cfg)
    assert ": Provides helper." in out


def test_render_full_includes_dependency_graph() -> None:
    modules = [
        ParsedModule(
            name="users",
            path="src/api/users.py",
            language="python",
            imports=["models.user", "db.session", "os"],
        ),
        ParsedModule(
            name="user",
            path="src/models/user.py",
            language="python",
            imports=[],
        ),
        ParsedModule(
            name="session",
            path="src/db/session.py",
            language="python",
            imports=["sqlalchemy"],
        ),
    ]
    cfg = LlmsTxtConfig(name="test")
    out = render_full(modules, cfg)

    assert "## Dependency Graph" in out
    assert "`src/api/users.py` imports: `src/db/session.py`, `src/models/user.py`" in out
    assert "`src/models/user.py` imports: (none — leaf node)" in out
    assert "`src/db/session.py` imports: (none — leaf node)" in out
    # Third party imports like 'os' and 'sqlalchemy' are filtered out
    assert "os" not in out.split("## src/api/users.py")[0]
    assert "sqlalchemy" not in out.split("## src/db/session.py")[0]
