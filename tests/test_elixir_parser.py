from pathlib import Path

import pytest
from llmstxt_gen.parsers.elixir import ElixirParser
from llmstxt_gen.walker import SourceFile

def test_parse_elixir_module():
    fixture_path = Path("tests/fixtures/sample_elixir/sample.ex")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="elixir", content=content)

    parser = ElixirParser()
    module = parser.parse(source_file)

    assert module.name == "sample"
    assert len(module.classes) == 3 # SampleModule.Core, SampleProtocol, SampleProtocol Integer implementation

    # Check SampleModule.Core
    core = next(c for c in module.classes if c.name == "SampleModule.Core")
    assert "A sample Elixir module for testing." in core.docstring
    assert "SampleBehaviour" in core.bases

    # Check constants and structs
    assert any(cv.name == "constant_attr" and cv.value == '"value"' for cv in core.class_vars)
    assert any(cv.name == "struct" and "[:name, :age]" in cv.value for cv in core.class_vars)

    # Check functions
    hello = next(f for f in core.methods if "hello" in f.name)
    assert hello.name == "hello"
    assert "Greets the user." in hello.docstring
    # Since we have @spec, it uses spec types
    assert len(hello.parameters) == 1
    assert hello.parameters[0].type_hint == "String.t()"

    multi = next(f for f in core.methods if "multi" in f.name)
    assert "multi (+1 heads)" == multi.name

    my_macro = next(f for f in core.methods if "my_macro" in f.name)
    assert my_macro.name == "my_macro"

    # Check private
    assert not any(f.name == "secret_func" for f in core.methods)

def test_parse_elixir_include_private():
    fixture_path = Path("tests/fixtures/sample_elixir/sample.ex")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="elixir", content=content)

    parser = ElixirParser(include_private=True)
    module = parser.parse(source_file)

    core = next(c for c in module.classes if c.name == "SampleModule.Core")
    assert any(f.name == "secret_func" for f in core.methods)

def test_parse_elixir_protocol():
    fixture_path = Path("tests/fixtures/sample_elixir/sample.ex")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="elixir", content=content)

    parser = ElixirParser()
    module = parser.parse(source_file)

    proto = next(c for c in module.classes if c.name == "SampleProtocol")
    assert any(m.name == "foo" for m in proto.methods)

    impl = next(c for c in module.classes if "SampleProtocol" in c.name and "Integer" in c.name)
    assert any(m.name == "foo" for m in impl.methods)
