from pathlib import Path

from llmstxt_gen.parsers.java import JavaParser
from llmstxt_gen.walker import SourceFile


def test_java_parser_basic():
    fixture_path = Path("tests/fixtures/sample_java/Sample.java")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="java", content=content)

    parser = JavaParser(include_private=False)
    module = parser.parse(source_file)

    assert module.name == "Sample"
    assert "Package-level Javadoc" in module.docstring

    # SampleClass
    cls = next(c for c in module.classes if c.name == "SampleClass")
    assert "A public class with Javadoc" in cls.docstring

    # Fields
    field = next(f for f in cls.class_vars if f.name == "publicField")
    assert field.type_hint == "String"

    # Methods
    method = next(m for m in cls.methods if m.name == "publicMethod")
    assert method.return_type == "String"
    assert method.parameters[0].name == "input"
    assert method.parameters[0].type_hint == "String"
    assert "@param input" in method.docstring

    # Constructor
    ctor = next(m for m in cls.methods if m.name == "SampleClass")
    assert ctor.return_type == ""

    # Protected method should be included
    assert any(m.name == "protectedMethod" for m in cls.methods)

    # Private and package-private should be excluded
    assert not any(m.name == "privateMethod" for m in cls.methods)
    assert not any(m.name == "packagePrivateMethod" for m in cls.methods)

    # Inner class
    inner_cls = next(c for c in module.classes if c.name == "SampleClass.InnerClass")
    assert any(m.name == "innerMethod" for m in inner_cls.methods)


def test_java_parser_interface_enum_record():
    fixture_path = Path("tests/fixtures/sample_java/Sample.java")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="java", content=content)

    parser = JavaParser(include_private=False)
    module = parser.parse(source_file)

    # Interface (non-public in fixture, but let's check)
    # Wait, SampleInterface is NOT public in my fixture.
    # "public interface" is needed for it to be exported.
    # Let me check the fixture.
    # Oh, SampleInterface is "interface SampleInterface". That's package-private.
    # So it should be excluded.
    assert not any(c.name == "SampleInterface" for c in module.classes)

    # SampleEnum is public
    enum_cls = next(c for c in module.classes if c.name == "SampleEnum")
    assert any(v.name == "VALUE1" for v in enum_cls.class_vars)

    # SampleRecord is public
    record_cls = next(c for c in module.classes if c.name == "SampleRecord")
    assert any(v.name == "name" and v.type_hint == "String" for v in record_cls.class_vars)
    assert any(v.name == "age" and v.type_hint == "int" for v in record_cls.class_vars)


def test_java_parser_generics_annotations():
    fixture_path = Path("tests/fixtures/sample_java/Sample.java")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="java", content=content)

    parser = JavaParser(include_private=True)  # Include private to see classes without public
    module = parser.parse(source_file)

    # GenericClass
    gen_cls = next(c for c in module.classes if "GenericClass" in c.name)
    assert gen_cls.name == "GenericClass<T extends Comparable<T>>"

    method = next(m for m in gen_cls.methods if m.name == "genericMethod")
    assert method.return_type == "<U> List<U>"

    # AnnotatedClass
    ann_cls = next(c for c in module.classes if c.name == "AnnotatedClass")
    method = next(m for m in ann_cls.methods if m.name == "annotatedMethod")
    assert "@Deprecated" in method.decorators
    assert '@SuppressWarnings("unchecked")' in method.decorators


def test_java_parser_include_private():
    fixture_path = Path("tests/fixtures/sample_java/Sample.java")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="java", content=content)

    parser = JavaParser(include_private=True)
    module = parser.parse(source_file)

    cls = next(c for c in module.classes if c.name == "SampleClass")
    assert any(m.name == "privateMethod" for m in cls.methods)
    assert any(m.name == "packagePrivateMethod" for m in cls.methods)
    assert any(f.name == "privateField" for f in cls.class_vars)

    assert any(c.name == "SampleInterface" for c in module.classes)
