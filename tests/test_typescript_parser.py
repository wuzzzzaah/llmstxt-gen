from pathlib import Path

from llmstxt_gen.parsers.typescript import TypeScriptParser
from llmstxt_gen.walker import SourceFile


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


def test_typescript_parser_marks_optional_parameters(sample_typescript_root: Path) -> None:
    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    fn = next(f for f in module.functions if f.name == "fetchItems")
    params = {p.name: p for p in fn.parameters}
    assert not params["id"].is_optional
    assert params["since"].is_optional
    assert params["limit"].is_optional


def test_renderer_emits_question_mark_for_optional_params(sample_typescript_root: Path) -> None:
    from llmstxt_gen.renderer import _format_signature

    parser = TypeScriptParser()
    module = parser.parse(_load(sample_typescript_root / "index.ts"))
    fn = next(f for f in module.functions if f.name == "fetchItems")
    sig = _format_signature(fn)
    assert "since?: string" in sig
    assert "limit?: number" in sig
    assert "id?: " not in sig  # id is required


def test_typescript_parser_reuses_parser_instances(sample_typescript_root: Path) -> None:
    parser = TypeScriptParser()

    # Capture initial parser instances
    js_parser = parser._js_parser
    ts_parser = parser._ts_parser
    tsx_parser = parser._tsx_parser

    # Call parse multiple times
    parser.parse(_load(sample_typescript_root / "index.ts"))
    parser.parse(_load(sample_typescript_root / "index.ts"))

    # Verify they are the same instances
    assert parser._js_parser is js_parser
    assert parser._ts_parser is ts_parser
    assert parser._tsx_parser is tsx_parser

    # Verify _parser_for returns the correct cached instance
    ts_file = _load(sample_typescript_root / "index.ts")
    assert parser._parser_for(ts_file) is ts_parser

    js_file = SourceFile(path=Path("test.js"), language="javascript", content="")
    assert parser._parser_for(js_file) is js_parser

    tsx_file = SourceFile(path=Path("test.tsx"), language="typescript", content="")
    assert parser._parser_for(tsx_file) is tsx_parser


def test_typescript_parser_extracts_zod_schema_shape() -> None:
    content = """
import { z } from 'zod';
export const createJourneySchema = z.object({
  title: z.string().min(1),
  description: z.string().optional(),
  age: z.number().int().optional(),
  isActive: z.boolean().default(true),
});
export const other = z.string();
"""
    parser = TypeScriptParser()
    module = parser.parse(SourceFile(path=Path("test.ts"), language="typescript", content=content))
    constants = {c.name: c for c in module.constants}

    assert "createJourneySchema" in constants
    # Condensed shape should be in type_hint
    assert (
        constants["createJourneySchema"].type_hint
        == "{ title: string, description?: string, age?: number, isActive: boolean }"
    )
    assert constants["other"].type_hint == ""  # Not an object, no condensed shape
