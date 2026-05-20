from pathlib import Path

from llmstxt_gen.parsers.kotlin import KotlinParser
from llmstxt_gen.walker import SourceFile


def test_kotlin_parser_basic():
    fixture_path = Path("tests/fixtures/sample_kotlin/Sample.kt")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="kotlin", content=content)

    parser = KotlinParser(include_private=False)
    module = parser.parse(source_file)

    assert module.name == "Sample"
    assert "Module-level KDoc" in module.docstring

    # SampleClass
    cls = next(c for c in module.classes if c.name.startswith("SampleClass"))
    assert cls.name == "SampleClass<T>"
    assert "A public class with KDoc" in cls.docstring

    # Properties in primary constructor
    prop = next(p for p in cls.class_vars if p.name == "publicProp")
    assert prop.type_hint == "String"

    # Private property in primary constructor should be excluded by default
    assert not any(p.name == "privateProp" for p in cls.class_vars)

    # Methods
    method = next(m for m in cls.methods if m.name == "publicMethod")
    assert method.return_type == "String"
    assert method.parameters[0].name == "input"
    assert method.parameters[0].type_hint == "String"
    # Some versions might have different spacing or quotes, but we expect it to match fixture
    assert method.parameters[0].default == '"default"'
    assert "A public method" in method.docstring

    # Protected method should be included
    assert any(m.name == "protectedMethod" for m in cls.methods)

    # Private and internal should be excluded
    assert not any(m.name == "privateMethod" for m in cls.methods)
    assert not any(m.name == "internalMethod" for m in cls.methods)

    # Companion object members
    assert any(m.name == "companionMethod" for m in cls.methods)
    assert any(p.name == "companionProp" for p in cls.class_vars)


def test_kotlin_parser_data_extension_top_level():
    fixture_path = Path("tests/fixtures/sample_kotlin/Sample.kt")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="kotlin", content=content)

    parser = KotlinParser(include_private=False)
    module = parser.parse(source_file)

    # Data class
    data_cls = next(c for c in module.classes if c.name == "SampleData")
    assert any(p.name == "x" and p.type_hint == "Int" for p in data_cls.class_vars)
    assert any(p.name == "y" and p.type_hint == "Int" for p in data_cls.class_vars)

    # Extension function
    ext_fn = next(f for f in module.functions if f.name == "String.shout")
    assert ext_fn.return_type == "String"

    # Top-level property
    prop = next(p for p in module.constants if p.name == "topLevelVal")
    assert prop.value == '"Hello"'

    # Private top-level should be excluded
    assert not any(p.name == "privateTopLevelVal" for p in module.constants)


def test_kotlin_parser_sealed_interface_enum_object():
    fixture_path = Path("tests/fixtures/sample_kotlin/Sample.kt")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="kotlin", content=content)

    parser = KotlinParser(include_private=False)
    module = parser.parse(source_file)

    # Sealed class
    assert any(c.name == "Expr" for c in module.classes)
    const_cls = next(c for c in module.classes if c.name == "Const")
    assert "Expr" in const_cls.bases

    # Interface
    assert any(c.name == "SampleInterface" for c in module.classes)

    # Enum
    enum_cls = next(c for c in module.classes if c.name == "Color")
    assert any(v.name == "RED" for v in enum_cls.class_vars)

    # Object
    obj_cls = next(c for c in module.classes if c.name == "Singleton")
    assert any(m.name == "greet" for m in obj_cls.methods)


def test_kotlin_parser_annotations():
    fixture_path = Path("tests/fixtures/sample_kotlin/Sample.kt")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="kotlin", content=content)

    parser = KotlinParser(include_private=False)
    module = parser.parse(source_file)

    fn = next(f for f in module.functions if f.name == "annotatedFun")
    # In my last implementation, I was struggling with annotations.
    # Let's hope it works now.
    assert any("Deprecated" in d for d in fn.decorators)


def test_kotlin_parser_include_private():
    fixture_path = Path("tests/fixtures/sample_kotlin/Sample.kt")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="kotlin", content=content)

    parser = KotlinParser(include_private=True)
    module = parser.parse(source_file)

    cls = next(c for c in module.classes if c.name.startswith("SampleClass"))
    assert any(m.name == "privateMethod" for m in cls.methods)
    assert any(m.name == "internalMethod" for m in cls.methods)
    assert any(p.name == "privateProp" for p in cls.class_vars)
    assert any(p.name == "privateTopLevelVal" for p in module.constants)
