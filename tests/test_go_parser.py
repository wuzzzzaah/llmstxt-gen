from pathlib import Path

from llmstxt_gen.parsers.go import GoParser
from llmstxt_gen.walker import SourceFile


def _load(path: Path) -> SourceFile:
    return SourceFile(path=path, language="go", content=path.read_text())


def test_go_parser_extracts_package_docstring(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    assert "sample Go package" in module.docstring


def test_go_parser_extracts_public_functions(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    names = [f.name for f in module.functions]
    assert "ExportedFunction" in names
    assert "unexportedFunction" not in names


def test_go_parser_extracts_structs_and_methods(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    cls = next(c for c in module.classes if c.name == "MyStruct")
    assert cls.docstring == "MyStruct is a sample struct."
    method_names = [m.name for m in cls.methods]
    assert "MyMethod" in method_names
    assert "unexportedMethod" not in method_names


def test_go_parser_extracts_interfaces(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    cls = next(c for c in module.classes if c.name == "MyInterface")
    assert "sample interface" in cls.docstring
    # Interfaces should have empty bases according to requirements
    assert cls.bases == []


def test_go_parser_extracts_interface_methods(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    cls = next(c for c in module.classes if c.name == "MyInterface")
    method_names = [m.name for m in cls.methods]
    assert "DoSomething" in method_names

    # Verify method details
    ds = next(m for m in cls.methods if m.name == "DoSomething")
    assert ds.return_type == "string"
    assert ds.docstring == "DoSomething is an interface method."


def test_go_parser_extracts_complex_interface_methods() -> None:
    parser = GoParser()
    content = """
package main
type ComplexInterface interface {
    // Method with params and returns
    DoMore(a int, b string) (int, error)
    // Simple method
    Simple()
}
"""
    sf = SourceFile(path=Path("complex.go"), language="go", content=content)
    module = parser.parse(sf)
    cls = next(c for c in module.classes if c.name == "ComplexInterface")

    assert len(cls.methods) == 2

    do_more = next(m for m in cls.methods if m.name == "DoMore")
    assert do_more.return_type == "(int, error)"
    assert len(do_more.parameters) == 2
    assert do_more.parameters[0].name == "a"
    assert do_more.parameters[0].type_hint == "int"
    assert do_more.parameters[1].name == "b"
    assert do_more.parameters[1].type_hint == "string"
    assert "Method with params and returns" in do_more.docstring

    simple = next(m for m in cls.methods if m.name == "Simple")
    assert simple.return_type == ""
    assert len(simple.parameters) == 0


def test_go_parser_extracts_constants_and_variables(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    const_names = [c.name for c in module.constants]
    assert "ExportedConstant" in const_names
    assert "ExportedVariable" in const_names
    assert "unexportedConstant" not in const_names
    assert "C1" in const_names
    assert "V1" in const_names


def test_go_parser_includes_private_when_requested(sample_go_root: Path) -> None:
    parser = GoParser(include_private=True)
    module = parser.parse(_load(sample_go_root / "main.go"))
    assert any(f.name == "unexportedFunction" for f in module.functions)
    assert any(c.name == "unexportedConstant" for c in module.constants)
    cls = next(c for c in module.classes if c.name == "MyStruct")
    assert any(m.name == "unexportedMethod" for m in cls.methods)


def test_go_parser_extracts_embedded_types(sample_go_root: Path) -> None:
    parser = GoParser()
    module = parser.parse(_load(sample_go_root / "main.go"))
    cls = next(c for c in module.classes if c.name == "EmbeddedStruct")
    assert "MyStruct" in cls.bases


def test_go_parser_handles_multiple_parameters_same_type() -> None:
    parser = GoParser()
    content = "package main\nfunc F(a, b int, c string) {}"
    sf = SourceFile(path=Path("test.go"), language="go", content=content)
    module = parser.parse(sf)
    fn = module.functions[0]
    assert len(fn.parameters) == 3
    assert fn.parameters[0].name == "a"
    assert fn.parameters[0].type_hint == "int"
    assert fn.parameters[1].name == "b"
    assert fn.parameters[1].type_hint == "int"
    assert fn.parameters[2].name == "c"
    assert fn.parameters[2].type_hint == "string"


def test_go_parser_handles_variadic_parameters() -> None:
    parser = GoParser()
    content = "package main\nfunc F(args ...string) {}"
    sf = SourceFile(path=Path("test.go"), language="go", content=content)
    module = parser.parse(sf)
    fn = module.functions[0]
    assert fn.parameters[0].name == "...args"
    assert fn.parameters[0].type_hint == "...string"


def test_go_parser_extracts_env_vars() -> None:
    content = """
package main
import "os"
func main() {
    val := os.Getenv("FOO_BAR")
    other := os.Getenv(`BAZ_QUX`)
}
"""
    parser = GoParser()
    module = parser.parse(SourceFile(path=Path("main.go"), language="go", content=content))
    assert module.env_vars == {
        "FOO_BAR": ["main.go"],
        "BAZ_QUX": ["main.go"],
    }
