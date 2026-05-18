from pathlib import Path

from codexa.parsers.typescript import TypeScriptParser
from codexa.walker import SourceFile


def _load(path: Path) -> SourceFile:
    return SourceFile(path=path, language="typescript", content=path.read_text())


def test_typescript_parser_extracts_exported_functions(sample_typescript_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    names = [f.name for f in module.functions]
    assert "add" in names
    assert "multiply" in names
    assert "notExported" not in names


def test_typescript_parser_extracts_exported_class(sample_typescript_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    assert any(c.name == "Greeter" for c in module.classes)
    greeter = next(c for c in module.classes if c.name == "Greeter")
    method_names = {m.name for m in greeter.methods}
    assert "greet" in method_names
    assert "_privateMethod" not in method_names


def test_typescript_parser_extracts_interface_and_type(sample_typescript_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    names = {c.name for c in module.constants}
    assert "Point" in names
    assert "Pair" in names
    assert "VERSION" in names
