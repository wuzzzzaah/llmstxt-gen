from pathlib import Path

from llmstxt_gen.parsers.cpp import CppParser
from llmstxt_gen.walker import SourceFile


def test_parse_c_functions():
    content = """
    /**
     * Adds two integers.
     */
    int add(int a, int b) {
        return a + b;
    }

    static void internal_func() {}
    """
    source_file = SourceFile(path=Path("test.c"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    assert len(module.functions) == 1
    assert module.functions[0].name == "add"
    assert module.functions[0].return_type == "int"
    assert "Adds two integers." in module.functions[0].docstring
    assert len(module.functions[0].parameters) == 2
    assert module.functions[0].parameters[0].name == "a"
    assert module.functions[0].parameters[0].type_hint == "int"

def test_parse_c_struct():
    content = """
    struct Point {
        int x;
        int y;
    };
    """
    source_file = SourceFile(path=Path("test.c"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    assert len(module.classes) == 1
    cls = module.classes[0]
    assert cls.name == "Point"
    assert len(cls.class_vars) == 2
    assert cls.class_vars[0].name == "x"
    assert cls.class_vars[0].type_hint == "int"

def test_parse_cpp_class_visibility():
    content = """
    class MyClass {
    public:
        void public_method();
    protected:
        void protected_method();
    private:
        void private_method();
        int x;
    };
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")

    # default: include_private=False
    parser = CppParser()
    module = parser.parse(source_file)
    assert len(module.classes) == 1
    cls = module.classes[0]
    assert len(cls.methods) == 1
    assert cls.methods[0].name == "public_method"
    assert len(cls.class_vars) == 0

    # include_private=True
    parser_priv = CppParser(include_private=True)
    module_priv = parser_priv.parse(source_file)
    cls_priv = module_priv.classes[0]
    assert len(cls_priv.methods) == 3
    assert len(cls_priv.class_vars) == 1

def test_parse_class_default_visibility():
    content = """
    class MyClass {
        void private_method();
    public:
        void public_method();
    };
    struct MyStruct {
        void public_method();
    private:
        void private_method();
    };
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    cls = next(c for c in module.classes if c.name == "MyClass")
    assert len(cls.methods) == 1
    assert cls.methods[0].name == "public_method"

    st = next(c for c in module.classes if c.name == "MyStruct")
    assert len(st.methods) == 1
    assert st.methods[0].name == "public_method"

def test_parse_templates():
    content = """
    template<typename T>
    class Box {
        T value;
    };

    template<typename T>
    T identity(T x) { return x; }
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    assert len(module.classes) == 1
    assert module.classes[0].name == "Box<typename T>"

    assert len(module.functions) == 1
    assert "template<typename T>" in module.functions[0].name
    assert "identity" in module.functions[0].name

def test_parse_enums_and_aliases():
    content = """
    enum Color { RED, GREEN, BLUE };
    typedef int my_int;
    using my_float = float;
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    assert len(module.classes) == 1
    assert module.classes[0].name == "Color"
    assert len(module.classes[0].class_vars) == 3

    assert len(module.constants) == 2
    assert any(c.name == "my_int" and c.type_hint == "int" for c in module.constants)
    assert any(c.name == "my_float" and c.type_hint == "float" for c in module.constants)

def test_parse_doxygen_comments():
    content = """
    /// Single line
    void func1();

    /**
     * Multi-line
     * Doxygen
     */
    void func2();
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    assert module.functions[0].docstring == "Single line"
    assert "Multi-line\nDoxygen" in module.functions[1].docstring

def test_parse_operator_overload_and_destructor():
    content = """
    class Complex {
    public:
        ~Complex();
        Complex operator+(const Complex& other);
    };
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    cls = module.classes[0]
    names = [m.name for m in cls.methods]
    assert "~Complex" in names
    assert "operator+" in names

def test_parse_pointer_and_reference_params():
    content = """
    void foo(int* p, const int& r, int arr[]);
    """
    source_file = SourceFile(path=Path("test.cpp"), content=content, language="cpp")
    parser = CppParser()
    module = parser.parse(source_file)

    fn = module.functions[0]
    assert fn.parameters[0].name == "p"
    assert fn.parameters[1].name == "r"
    assert fn.parameters[2].name == "arr"
