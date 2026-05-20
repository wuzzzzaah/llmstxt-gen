from pathlib import Path

from llmstxt_gen.parsers.php import PHPParser
from llmstxt_gen.walker import SourceFile


def test_php_parser_basic():
    fixture_path = Path("tests/fixtures/sample_php/Sample.php")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="php", content=content)

    parser = PHPParser(include_private=False)
    module = parser.parse(source_file)

    assert module.name == "Sample"
    assert "File-level PHPDoc" in module.docstring

    # SampleClass
    cls = next(c for c in module.classes if c.name == "SampleClass")
    assert "A public class with PHPDoc" in cls.docstring
    assert "BaseClass" in cls.bases
    assert "SampleInterface" in cls.bases

    # Constants
    const = next(c for c in cls.class_vars if c.name == "PUBLIC_CONST")
    assert const.value == "'value'"

    # Properties
    prop = next(c for c in cls.class_vars if c.name == "$publicProp")
    assert prop.type_hint == "string"
    assert prop.value == "'default'"

    # Methods
    method = next(m for m in cls.methods if m.name == "publicMethod")
    assert method.return_type == "string"
    assert len(method.parameters) == 1
    assert method.parameters[0].name == "$input"
    assert method.parameters[0].type_hint == "string"
    assert "@param string $input" in method.docstring

    # Unscoped method should be public
    assert any(m.name == "unscopedMethod" for m in cls.methods)

    # Protected method should be EXCLUDED by default now
    assert not any(m.name == "protectedMethod" for m in cls.methods)
    assert not any(c.name == "$protectedProp" for c in cls.class_vars)

    # Private should be excluded
    assert not any(m.name == "privateMethod" for m in cls.methods)
    assert not any(c.name == "$privateProp" for c in cls.class_vars)


def test_php_parser_global_function():
    fixture_path = Path("tests/fixtures/sample_php/Sample.php")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="php", content=content)

    parser = PHPParser()
    module = parser.parse(source_file)

    fn = next(f for f in module.functions if f.name == "globalFunction")
    assert fn.return_type == "void"
    assert fn.parameters[0].name == "$x"
    assert fn.parameters[0].type_hint == "int"
    assert fn.parameters[1].name == "$y"
    assert fn.parameters[1].default == "10"


def test_php_parser_interface_trait_enum():
    fixture_path = Path("tests/fixtures/sample_php/Sample.php")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="php", content=content)

    parser = PHPParser()
    module = parser.parse(source_file)

    # Interface
    iface = next(c for c in module.classes if c.name == "SampleInterface")
    assert any(m.name == "foo" for m in iface.methods)
    assert len(iface.bases) == 0 # Requirement: interfaces have empty bases

    # Trait
    trait = next(c for c in module.classes if c.name == "SampleTrait")
    assert any(m.name == "traitMethod" for m in trait.methods)

    # Enum
    enum = next(c for c in module.classes if c.name == "SampleEnum")
    assert any(v.name == "A" and v.value == "'a'" for v in enum.class_vars)
    assert any(v.name == "B" and v.value == "'b'" for v in enum.class_vars)


def test_php_parser_include_private():
    fixture_path = Path("tests/fixtures/sample_php/Sample.php")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="php", content=content)

    parser = PHPParser(include_private=True)
    module = parser.parse(source_file)

    cls = next(c for c in module.classes if c.name == "SampleClass")
    assert any(m.name == "privateMethod" for m in cls.methods)
    assert any(m.name == "protectedMethod" for m in cls.methods)
    assert any(c.name == "$privateProp" for c in cls.class_vars)
    assert any(c.name == "$protectedProp" for c in cls.class_vars)


def test_php_parser_variadic_and_empty():
    content = """<?php
    function variadic(...$args) {}
    function no_params() {}
    """
    source_file = SourceFile(path=Path("test.php"), language="php", content=content)
    parser = PHPParser()
    module = parser.parse(source_file)

    fn = next(f for f in module.functions if f.name == "variadic")
    assert fn.parameters[0].name == "...$args"

    fn2 = next(f for f in module.functions if f.name == "no_params")
    assert len(fn2.parameters) == 0

def test_php_parser_namespace_with_braces():
    content = """<?php
    namespace Foo {
        class Bar {}
    }
    """
    source_file = SourceFile(path=Path("test.php"), language="php", content=content)
    parser = PHPParser()
    module = parser.parse(source_file)
    assert any(c.name == "Bar" for c in module.classes)

def test_php_parser_return_type_fallback():
    # Force fallback if possible, though return_type field should exist
    content = """<?php
    function foo(): MyType {}
    """
    source_file = SourceFile(path=Path("test.php"), language="php", content=content)
    parser = PHPParser()
    module = parser.parse(source_file)
    assert module.functions[0].return_type == "MyType"
