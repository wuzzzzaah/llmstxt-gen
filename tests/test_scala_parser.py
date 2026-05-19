from pathlib import Path
from llmstxt_gen.parsers.scala import ScalaParser
from llmstxt_gen.walker import SourceFile

def test_scala_parser_basic():
    content = """
    package test

    /**
     * A test class
     */
    class TestClass(val x: Int) extends Base {
      /** A method */
      def method(y: String): Int = 42
    }

    object TestClass {
      def companionMethod(): Unit = ()
    }

    case class Person(name: String, age: Int = 20)

    trait MyTrait {
      def traitMethod(): String
    }

    enum MyEnum {
      case A, B
    }

    private class PrivateClass
    """
    parser = ScalaParser()
    source_file = SourceFile(Path("test.scala"), "scala", content)
    module = parser.parse(source_file)

    assert module.name == "test"

    # We expect 5 classes (TestClass, Person, MyTrait, MyEnum, and potentially others if any)
    # TestClass should have merged companionMethod
    classes = {c.name: c for c in module.classes}

    assert "TestClass" in classes
    tc = classes["TestClass"]
    assert tc.docstring == "A test class"
    assert tc.bases == ["Base"]

    methods = {m.name: m for m in tc.methods}
    assert "method" in methods
    assert methods["method"].docstring == "A method"
    assert methods["method"].return_type == "Int"
    assert len(methods["method"].parameters) == 1
    assert methods["method"].parameters[0].name == "y"
    assert methods["method"].parameters[0].type_hint == "String"

    assert "companionMethod" in methods

    assert "Person" in classes
    person = classes["Person"]
    # Case class parameters should be in class_vars
    cvars = {cv.name: cv for cv in person.class_vars}
    assert "name" in cvars
    assert cvars["name"].type_hint == "String"
    assert "age" in cvars
    assert cvars["age"].type_hint == "Int"
    assert cvars["age"].value == "20"

    assert "MyTrait" in classes
    assert "MyEnum" in classes
    enum_cls = classes["MyEnum"]
    enum_vars = {cv.name: cv for cv in enum_cls.class_vars}
    assert "A" in enum_vars
    assert "B" in enum_vars

    # Private class should be skipped
    assert "PrivateClass" not in classes

def test_scala_parser_private():
    content = """
    private class PrivateClass
    class PublicClass {
      private def privateMethod() = 1
    }
    """
    parser = ScalaParser(include_private=True)
    source_file = SourceFile(Path("test.scala"), "scala", content)
    module = parser.parse(source_file)

    classes = {c.name: c for c in module.classes}
    assert "PrivateClass" in classes
    assert "PublicClass" in classes
    pc = classes["PublicClass"]
    assert any(m.name == "privateMethod" for m in pc.methods)

def test_scala_parser_scala3():
    content = """
    extension (s: String) {
      def shouting: String = s.toUpperCase
    }

    given intOrd: Ordering[Int] with {
      def compare(x: Int, y: Int) = x - y
    }
    """
    parser = ScalaParser()
    source_file = SourceFile(Path("test.scala"), "scala", content)
    module = parser.parse(source_file)

    functions = {f.name: f for f in module.functions}
    assert "extension (s: String) shouting" in functions
    assert "given intOrd" in functions
    assert functions["given intOrd"].return_type == "Ordering[Int]"

def test_scala_parser_implicits():
    content = """
    def foo(implicit x: Int): Unit
    def bar(using y: String): Unit
    """
    parser = ScalaParser()
    source_file = SourceFile(Path("test.scala"), "scala", content)
    module = parser.parse(source_file)

    functions = {f.name: f for f in module.functions}
    assert "foo" in functions
    assert functions["foo"].parameters[0].name == "implicit x"
    assert "bar" in functions
    assert functions["bar"].parameters[0].name == "using y"

def test_scala_parser_companion_order():
    content = """
    object MyClass {
      def companionMethod() = 1
    }
    class MyClass(val x: Int)
    """
    parser = ScalaParser()
    source_file = SourceFile(Path("test.scala"), "scala", content)
    module = parser.parse(source_file)

    classes = {c.name: c for c in module.classes}
    assert "MyClass" in classes
    mc = classes["MyClass"]
    assert any(m.name == "companionMethod" for m in mc.methods)
    assert any(cv.name == "x" for cv in mc.class_vars)

def test_scala_parser_fixture():
    fixture_path = Path("tests/fixtures/sample_scala/Main.scala")
    content = fixture_path.read_text()
    parser = ScalaParser()
    source_file = SourceFile(fixture_path, "scala", content)
    module = parser.parse(source_file)

    classes = {c.name: c for c in module.classes}
    assert "Main" in classes
    assert "Greeter" in classes
    assert "Person" in classes
    assert "Color" in classes

    # Check Greeter merged with companion object
    greeter = classes["Greeter"]
    methods = {m.name: m for m in greeter.methods}
    assert "greet" in methods
    assert "defaultPrefix" in methods
