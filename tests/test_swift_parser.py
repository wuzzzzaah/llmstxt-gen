from pathlib import Path
from llmstxt_gen.parsers.swift import SwiftParser
from llmstxt_gen.walker import SourceFile

def test_swift_parser_basic():
    content = """
    /// Module docs
    import Foundation

    /// A greeter protocol
    public protocol Greeter {
        /// Greets
        func greet() -> String
        /// Prop
        var version: Int { get }
    }

    /// A person class
    public class Person: Greeter {
        public let name: String
        private let secret = "shh"

        public init(name: String) {
            self.name = name
        }

        public func greet() -> String {
            return "Hi"
        }

        public var version: Int { return 1 }
    }

    public enum Color {
        case red, blue
    }

    extension Person {
        public func walk() {}
    }

    /// Global func
    public func add(a: Int, b: Int) -> Int {
        return a + b
    }
    """
    source = SourceFile(path=Path("main.swift"), language="swift", content=content)
    parser = SwiftParser()
    module = parser.parse(source)

    assert module.name == "main"
    assert "Module docs" in module.docstring

    # Functions
    assert len(module.functions) == 1
    assert module.functions[0].name == "add"
    assert len(module.functions[0].parameters) == 2

    # Classes (protocol, class, enum)
    assert {c.name for c in module.classes} == {"Greeter", "Person", "Color"}

    greeter = next(c for c in module.classes if c.name == "Greeter")
    assert "A greeter protocol" in greeter.docstring
    assert len(greeter.methods) == 2
    assert any(m.name == "greet" for m in greeter.methods)
    assert any(m.name == "version" and m.is_property for m in greeter.methods)

    person = next(c for c in module.classes if c.name == "Person")
    assert "A person class" in person.docstring
    # name (prop), init, greet, version (prop), walk (from extension)
    assert len(person.methods) == 5
    assert any(m.name == "init" for m in person.methods)
    assert any(m.name == "greet" for m in person.methods)
    assert any(m.name == "walk" for m in person.methods)
    assert any(m.name == "name" and m.is_property for m in person.methods)
    assert any(m.name == "version" and m.is_property for m in person.methods)

    color = next(c for c in module.classes if c.name == "Color")
    assert len(color.class_vars) == 2
    assert {v.name for v in color.class_vars} == {"red", "blue"}

def test_swift_parser_include_private():
    content = """
    public func publicFunc() {}
    private func privateFunc() {}
    """
    source = SourceFile(path=Path("main.swift"), language="swift", content=content)

    parser = SwiftParser(include_private=False)
    module = parser.parse(source)
    assert len(module.functions) == 1
    assert module.functions[0].name == "publicFunc"

    parser = SwiftParser(include_private=True)
    module = parser.parse(source)
    assert len(module.functions) == 2

def test_swift_parser_actor_and_macro():
    content = """
    @available(iOS 13, *)
    public actor MyActor {
        public func act() {}
    }

    @macro
    public macro MyMacro(a: Int) = #externalMacro(...)
    """
    source = SourceFile(path=Path("main.swift"), language="swift", content=content)
    parser = SwiftParser()
    module = parser.parse(source)

    actor = next(c for c in module.classes if c.name == "MyActor")
    assert any(m.name == "act" for m in actor.methods)

    macro = next(f for f in module.functions if f.name == "MyMacro")
    assert "@macro" in macro.decorators

def test_swift_parser_async_throws():
    content = """
    public func doWork() async throws -> String { "" }
    """
    source = SourceFile(path=Path("main.swift"), language="swift", content=content)
    parser = SwiftParser()
    module = parser.parse(source)

    fn = module.functions[0]
    assert fn.is_async
    assert "throws" in fn.return_type
