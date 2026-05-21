"""Tests for HTTP route extraction — Express (#37) and Next.js App Router (#39)."""

from pathlib import Path

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.parsers.python import PythonParser
from llmstxt_gen.parsers.typescript import TypeScriptParser
from llmstxt_gen.renderer import render_full
from llmstxt_gen.walker import SourceFile


def _load(path: Path, language: str = "typescript") -> SourceFile:
    return SourceFile(path=path, language=language, content=path.read_text())


# ---------------------------------------------------------------------------
# Express route extraction (#37)
# ---------------------------------------------------------------------------


def test_express_extracts_get_post_put_delete(sample_express_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_express_root / "server.ts"))
    methods = {r.method for r in module.routes}
    assert "GET" in methods
    assert "POST" in methods
    assert "PUT" in methods
    assert "DELETE" in methods


def test_express_extracts_correct_paths(sample_express_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_express_root / "server.ts"))
    paths = {r.path for r in module.routes}
    assert "/users" in paths
    assert "/users/:id" in paths


def test_express_captures_named_handler(sample_express_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_express_root / "server.ts"))
    put_route = next(r for r in module.routes if r.method == "PUT")
    assert put_route.handler == "updateUser"


def test_express_records_line_numbers(sample_express_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_express_root / "server.ts"))
    get_route = next(r for r in module.routes if r.method == "GET" and r.path == "/users")
    assert get_route.line > 0


# ---------------------------------------------------------------------------
# Next.js App Router route inference (#39)
# ---------------------------------------------------------------------------


def test_nextjs_route_file_extracts_http_verbs(sample_nextjs_root: Path) -> None:
    parser = TypeScriptParser()
    route_file = sample_nextjs_root / "app" / "api" / "users" / "route.ts"
    module = parser.parse(_load(route_file))
    methods = {r.method for r in module.routes}
    assert "GET" in methods
    assert "POST" in methods


def test_nextjs_route_file_has_correct_url_path(sample_nextjs_root: Path) -> None:
    parser = TypeScriptParser()
    route_file = sample_nextjs_root / "app" / "api" / "users" / "route.ts"
    module = parser.parse(_load(route_file))
    for route in module.routes:
        assert route.path == "/api/users"


def test_nextjs_page_file_infers_get_route(sample_nextjs_root: Path) -> None:
    parser = TypeScriptParser()
    page_file = sample_nextjs_root / "app" / "page.tsx"
    module = parser.parse(_load(page_file))
    assert any(r.method == "GET" and r.path == "/" for r in module.routes)


def test_nextjs_non_route_file_has_no_routes(sample_typescript_root: Path) -> None:
    """Regular TypeScript files should not produce spurious routes."""
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    assert module.routes == []


# ---------------------------------------------------------------------------
# Renderer emits ### Routes section
# ---------------------------------------------------------------------------


def test_renderer_emits_routes_section(sample_express_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_express_root / "server.ts"))
    cfg = LlmsTxtConfig(name="demo")
    out = render_full([module], cfg)
    assert "### Routes" in out
    assert "`GET /users`" in out
    assert "`POST /users`" in out


def test_renderer_shows_named_handler(sample_express_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_express_root / "server.ts"))
    cfg = LlmsTxtConfig(name="demo")
    out = render_full([module], cfg)
    assert "→ `updateUser`" in out


def test_renderer_skips_routes_section_when_empty(sample_typescript_root: Path) -> None:
    """Modules without routes should not have a ### Routes heading."""
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    cfg = LlmsTxtConfig(name="demo")
    out = render_full([module], cfg)
    assert "### Routes" not in out


# ---------------------------------------------------------------------------
# Python route extraction (#41)
# ---------------------------------------------------------------------------


def test_python_extracts_fastapi_and_flask_routes(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "routes.py", "python"))
    methods = {r.method for r in module.routes}
    assert "GET" in methods
    assert "POST" in methods
    assert "PUT" in methods
    assert "PATCH" in methods


def test_python_renderer_emits_routes_section(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "routes.py", "python"))
    cfg = LlmsTxtConfig(name="demo")
    out = render_full([module], cfg)
    assert "### Routes" in out
    assert "`GET /users`" in out
    assert "`POST /users/{id}`" in out
    assert "`GET /legacy`" in out
