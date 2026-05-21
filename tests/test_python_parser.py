from pathlib import Path

from llmstxt_gen.parsers.python import PythonParser
from llmstxt_gen.walker import SourceFile


def _load(path: Path) -> SourceFile:
    return SourceFile(path=path, language="python", content=path.read_text())


def test_python_parser_extracts_module_docstring(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "calculator.py"))
    assert "calculator" in module.docstring.lower()


def test_python_parser_extracts_public_functions(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "calculator.py"))
    names = [f.name for f in module.functions]
    assert "add" in names
    assert "fetch" in names
    assert "_private_helper" not in names


def test_python_parser_extracts_async_functions(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "calculator.py"))
    fetch = next(f for f in module.functions if f.name == "fetch")
    assert fetch.is_async is True


def test_python_parser_extracts_classes_and_methods(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "calculator.py"))
    assert len(module.classes) == 1
    cls = module.classes[0]
    assert cls.name == "Calculator"
    method_names = [m.name for m in cls.methods]
    assert "add" in method_names
    assert "doubled" in method_names
    assert "_internal" not in method_names
    doubled = next(m for m in cls.methods if m.name == "doubled")
    assert doubled.is_property is True


def test_python_parser_includes_private_when_requested(sample_python_root: Path) -> None:
    parser = PythonParser(include_private=True)
    module = parser.parse(_load(sample_python_root / "calculator.py"))
    assert any(f.name == "_private_helper" for f in module.functions)


def test_python_parser_handles_function_without_docstring() -> None:
    parser = PythonParser()
    sf = SourceFile(
        path=Path("snippet.py"), language="python", content="def f(x: int) -> int:\n    return x\n"
    )
    module = parser.parse(sf)
    assert module.functions[0].docstring == ""
    assert module.functions[0].return_type == "int"


def test_python_parser_extracts_env_vars() -> None:
    content = """
import os
db_url = os.environ["DATABASE_URL"]
api_key = os.environ.get("API_KEY")
token = os.getenv("AUTH_TOKEN")
"""
    parser = PythonParser()
    module = parser.parse(SourceFile(path=Path("test.py"), language="python", content=content))
    assert module.env_vars == {
        "DATABASE_URL": ["test.py"],
        "API_KEY": ["test.py"],
        "AUTH_TOKEN": ["test.py"],
    }


def test_python_parser_extracts_routes(sample_python_root: Path) -> None:
    parser = PythonParser()
    module = parser.parse(_load(sample_python_root / "routes.py"))

    # list_users: @app.get("/users")
    list_users = next(r for r in module.routes if r.handler == "list_users")
    assert list_users.method == "GET"
    assert list_users.path == "/users"
    assert "List all users" in list_users.docstring

    # create_user: @router.post("/users/{id}")
    create_user = next(r for r in module.routes if r.handler == "create_user")
    assert create_user.method == "POST"
    assert create_user.path == "/users/{id}"

    # legacy_route: @app.route("/legacy", methods=["GET", "POST"])
    legacy_get = next(
        r for r in module.routes if r.handler == "legacy_route" and r.method == "GET"
    )
    assert legacy_get.path == "/legacy"
    legacy_post = next(
        r for r in module.routes if r.handler == "legacy_route" and r.method == "POST"
    )
    assert legacy_post.path == "/legacy"

    # update_item: @app.put("/items/{item_id}") AND @app.patch("/items/{item_id}")
    put_route = next(r for r in module.routes if r.handler == "update_item" and r.method == "PUT")
    patch_route = next(
        r for r in module.routes if r.handler == "update_item" and r.method == "PATCH"
    )
    assert put_route.path == "/items/{item_id}"
    assert patch_route.path == "/items/{item_id}"


def test_python_parser_extracts_imports() -> None:
    content = """
import os
import sys as s
from datetime import datetime
from .models import User
from .. import utils
"""
    parser = PythonParser()
    module = parser.parse(SourceFile(path=Path("test.py"), language="python", content=content))
    assert "os" in module.imports
    assert "sys" in module.imports
    assert "datetime" in module.imports
    assert ".models" in module.imports
    assert ".." in module.imports
