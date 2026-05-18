from pathlib import Path

import pytest

from llmstxt_gen.parsers.csharp import CSharpParser
from llmstxt_gen.walker import SourceFile


@pytest.fixture
def parser():
    return CSharpParser()

@pytest.fixture
def sample_cs():
    path = Path("tests/fixtures/sample_csharp/Sample.cs")
    return SourceFile(
        path=path,
        language="csharp",
        content=path.read_text()
    )

def test_parse_classes(parser, sample_cs):
    module = parser.parse(sample_cs)

    # PublicClass, IService (interface as ParsedClass), Status (enum as ParsedClass),
    # User (record as ParsedClass), Point (struct as ParsedClass), PartialClass
    class_names = [c.name for c in module.classes]
    assert "PublicClass" in class_names
    assert "IService" in class_names
    assert "Status" in class_names
    assert "User" in class_names
    assert "Point" in class_names
    assert "PartialClass" in class_names

    # Check PublicClass members
    pc = next(c for c in module.classes if c.name == "PublicClass")
    assert "A public class with XML docs." in pc.docstring

    method_names = [m.name for m in pc.methods]
    assert "Name" in method_names  # Property
    assert "DoSomething" in method_names
    assert "Identity<T> where T : class" in method_names
    assert "ProtectedMethod" in method_names
    assert "PrivateMethod" not in method_names

    # Verify method return types
    do_something = next(m for m in pc.methods if m.name == "DoSomething")
    assert do_something.return_type == "void"

    identity = next(m for m in pc.methods if m.name == "Identity<T> where T : class")
    assert identity.return_type == "T"

def test_parse_interface(parser, sample_cs):
    module = parser.parse(sample_cs)
    svc = next(c for c in module.classes if c.name == "IService")
    method_names = [m.name for m in svc.methods]
    assert "Run" in method_names
    assert svc.methods[0].return_type == "void"

def test_parse_property(parser, sample_cs):
    module = parser.parse(sample_cs)
    pc = next(c for c in module.classes if c.name == "PublicClass")
    prop = next(m for m in pc.methods if m.name == "Name")
    assert prop.is_property is True
    assert prop.return_type == "string"
    assert "A public property." in prop.docstring

def test_parse_attribute(parser, sample_cs):
    module = parser.parse(sample_cs)
    pc = next(c for c in module.classes if c.name == "PublicClass")
    method = next(m for m in pc.methods if m.name == "DoSomething")
    assert 'Obsolete("Use something else")' in method.decorators

def test_parse_record(parser, sample_cs):
    module = parser.parse(sample_cs)
    record = next(c for c in module.classes if c.name == "User")
    class_var_names = [v.name for v in record.class_vars]
    assert "Id" in class_var_names
    assert "Email" in class_var_names

def test_parse_enum(parser, sample_cs):
    module = parser.parse(sample_cs)
    enm = next(c for c in module.classes if c.name == "Status")
    assert len(enm.class_vars) == 2
    assert enm.class_vars[0].name == "Active"
    assert enm.class_vars[1].name == "Inactive"

def test_partial_class_merging(parser, sample_cs):
    module = parser.parse(sample_cs)
    partial_classes = [c for c in module.classes if c.name == "PartialClass"]
    assert len(partial_classes) == 1

    method_names = [m.name for m in partial_classes[0].methods]
    assert "Part1" in method_names
    assert "Part2" in method_names

def test_include_private(sample_cs):
    parser = CSharpParser(include_private=True)
    module = parser.parse(sample_cs)
    pc = next(c for c in module.classes if c.name == "PublicClass")
    method_names = [m.name for m in pc.methods]
    assert "PrivateMethod" in method_names
