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
