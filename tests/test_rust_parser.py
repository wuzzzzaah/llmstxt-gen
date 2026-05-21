from pathlib import Path

from llmstxt_gen.parsers.rust import RustParser
from llmstxt_gen.walker import SourceFile


def test_rust_parser_basic():
    fixture_path = Path("tests/fixtures/sample_rust/lib.rs")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="rust", content=content)

    parser = RustParser(include_private=False)
    module = parser.parse(source_file)

    assert module.name == "lib"
    assert "This is a module doc comment." in module.docstring

    # Public function
    pub_fns = [f for f in module.functions if "public_fn" in f.name]
    assert len(pub_fns) == 1
    assert pub_fns[0].return_type == "T"
    assert "A public function." in pub_fns[0].docstring
    # name includes generics and where clause
    assert "public_fn<T> where T: Clone" in pub_fns[0].name

    # Visibility
    crate_vis = [f for f in module.functions if f.name == "crate_visible"]
    assert len(crate_vis) == 1

    super_vis = [f for f in module.functions if f.name == "super_visible"]
    assert len(super_vis) == 1

    private_fns = [f for f in module.functions if f.name == "private_fn"]
    assert len(private_fns) == 0

    # Struct
    my_struct = next(c for c in module.classes if c.name == "MyStruct")
    assert "A public struct." in my_struct.docstring
    assert len(my_struct.class_vars) == 1
    assert my_struct.class_vars[0].name == "field"
    assert my_struct.class_vars[0].type_hint == "i32"

    # Impl methods
    new_method = next(m for m in my_struct.methods if m.name == "new")
    assert new_method.return_type == "Self"
    assert len(new_method.parameters) == 1
    assert new_method.parameters[0].name == "field"

    # Private method should be filtered out
    assert not any(m.name == "private_method" for m in my_struct.methods)

    # Enum
    my_enum = next(c for c in module.classes if c.name == "MyEnum")
    assert len(my_enum.class_vars) == 2
    assert any(v.name == "VariantA" for v in my_enum.class_vars)
    assert any(v.name == "VariantB" for v in my_enum.class_vars)

    # Trait
    my_trait = next(c for c in module.classes if "MyTrait" in c.name)
    assert "MyTrait<T> where T: Clone" in my_trait.name
    assert any("trait_method<U> where U: std::fmt::Display" in m.name for m in my_trait.methods)
    assert any(m.name == "provided_method" for m in my_trait.methods)

    # Trait impl
    # In my implementation, methods from 'impl MyTrait for MyStruct' are attached to MyStruct.
    trait_impl_method = next(m for m in my_struct.methods if m.name == "trait_method")
    assert trait_impl_method is not None

    # Constants and Statics
    assert any(c.name == "MY_CONST" for c in module.constants)
    assert any(c.name == "MY_STATIC" for c in module.constants)

    # Type Alias
    my_alias = next(c for c in module.constants if c.name == "MyAlias")
    assert my_alias.type_hint == "Vec<MyStruct>"


def test_rust_parser_include_private():
    fixture_path = Path("tests/fixtures/sample_rust/lib.rs")
    content = fixture_path.read_text()
    source_file = SourceFile(path=fixture_path, language="rust", content=content)

    parser = RustParser(include_private=True)
    module = parser.parse(source_file)

    assert any(f.name == "private_fn" for f in module.functions)

    my_struct = next(c for c in module.classes if c.name == "MyStruct")
    assert any(m.name == "private_method" for m in my_struct.methods)
    assert any(v.name == "private_field" for v in my_struct.class_vars)
