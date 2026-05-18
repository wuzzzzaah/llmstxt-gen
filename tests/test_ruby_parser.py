from pathlib import Path

from llmstxt_gen.parsers.ruby import RubyParser
from llmstxt_gen.walker import SourceFile


def test_ruby_parser_basic():
    fixture_path = Path("tests/fixtures/sample_ruby/sample.rb")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="ruby", content=content)

    parser = RubyParser(include_private=False)
    module = parser.parse(source_file)

    assert module.name == "sample"

    # Top-level method
    assert len(module.functions) == 1
    fn = module.functions[0]
    assert fn.name == "top_level_method"
    assert "Top level comment" in fn.docstring
    assert "@param x [Integer]" in fn.docstring
    assert len(fn.parameters) == 1
    assert fn.parameters[0].name == "x"

    # Module
    assert len(module.classes) == 2
    mod = next(c for c in module.classes if c.name == "MyModule")
    assert mod.docstring == "Module comment"
    assert len(mod.methods) == 1
    assert mod.methods[0].name == "module_method"

    # Class
    cls = next(c for c in module.classes if c.name == "MyClass")
    assert cls.docstring == "Class comment"
    assert "MyBase" in cls.bases
    assert "include(MyMixin)" in cls.bases
    assert "extend(MyExtend)" in cls.bases
    assert "prepend(MyPrepend)" in cls.bases

    # attr_* expansion
    # name (accessor) -> name and name=
    # age (reader) -> age
    # secret (writer) -> secret=
    # initialize, public_method
    method_names = [m.name for m in cls.methods]
    assert "name" in method_names
    assert "name=" in method_names
    assert "age" in method_names
    assert "secret=" in method_names
    assert "initialize" in method_names
    assert "public_method" in method_names

    # Visibility
    assert "protected_method" not in method_names
    assert "private_method" not in method_names

    # Constants
    assert len(mod.class_vars) == 1
    assert mod.class_vars[0].name == "MY_CONST"
    assert mod.class_vars[0].value == '"hello"'

def test_ruby_parser_include_private():
    fixture_path = Path("tests/fixtures/sample_ruby/sample.rb")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="ruby", content=content)

    parser = RubyParser(include_private=True)
    module = parser.parse(source_file)

    cls = next(c for c in module.classes if c.name == "MyClass")
    method_names = [m.name for m in cls.methods]

    assert "protected_method" in method_names
    assert "private_method" in method_names

    # Verify is_private flag
    protected_fn = next(m for m in cls.methods if m.name == "protected_method")
    assert protected_fn.is_private is True

    private_fn = next(m for m in cls.methods if m.name == "private_method")
    assert private_fn.is_private is True

    public_fn = next(m for m in cls.methods if m.name == "public_method")
    assert public_fn.is_private is False

def test_ruby_parser_parameter_types():
    content = """
def complex_params(a, b=1, *args, **kwargs, &block, k: 2)
end
"""
    source_file = SourceFile(path=Path("test.rb"), language="ruby", content=content)
    parser = RubyParser()
    module = parser.parse(source_file)

    fn = module.functions[0]
    params = {p.name: p for p in fn.parameters}

    assert "a" in params
    assert "b" in params
    assert params["b"].default == "1"
    assert "*args" in params
    assert "**kwargs" in params
    assert "&block" in params
    assert "k:" in params
    assert params["k:"].default == "2"

def test_ruby_parser_nested():
    content = """
module A
  class B
    def foo
    end
  end
end
"""
    source_file = SourceFile(path=Path("test.rb"), language="ruby", content=content)
    parser = RubyParser()
    module = parser.parse(source_file)

    assert len(module.classes) == 1
    assert module.classes[0].name == "A"
    # Nested B is not currently surfaced at top level by this implementation,
    # which matches how Python parser handles nested classes (it ignores them if not explicitly handled).
    # But let's check what it does.

def test_ruby_parser_modifier_visibility():
    content = """
class Foo
  def bar; end
  private def baz; end
  private :bar
end
"""
    source_file = SourceFile(path=Path("test.rb"), language="ruby", content=content)
    parser = RubyParser(include_private=False)
    module = parser.parse(source_file)

    cls = module.classes[0]
    method_names = [m.name for m in cls.methods]
    # 'baz' should be private because of 'private def baz'
    assert "baz" not in method_names

def test_ruby_parser_scoped_superclass():
    content = "class A < Scoped::Base; end"
    source_file = SourceFile(path=Path("test.rb"), language="ruby", content=content)
    parser = RubyParser()
    module = parser.parse(source_file)
    assert module.classes[0].bases == ["Scoped::Base"]

def test_ruby_parser_attr_visibility():
    content = """
class Foo
  private
  attr_accessor :secret
end
"""
    source_file = SourceFile(path=Path("test.rb"), language="ruby", content=content)
    parser = RubyParser(include_private=False)
    module = parser.parse(source_file)
    assert len(module.classes[0].methods) == 0

    parser = RubyParser(include_private=True)
    module = parser.parse(source_file)
    assert len(module.classes[0].methods) == 2
    assert module.classes[0].methods[0].is_private is True
