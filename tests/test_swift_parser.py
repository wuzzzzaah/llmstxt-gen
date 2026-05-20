from pathlib import Path

from llmstxt_gen.parsers.swift import SwiftParser
from llmstxt_gen.walker import SourceFile


def test_swift_parser_comprehensive():
    content = """
/**
 * Module documentation
 */
import Foundation

/// A protocol with property and method
public protocol Service {
    var id: String { get }
    func start() async throws
}

/// A struct
struct Config {
    let timeout: Int = 30
}

/// A class with init and extension
public class Manager {
    public init() {}
}

extension Manager {
    public func manage() {}
}

/// Extension for unknown type
extension String {
    public func localized() -> String { self }
}

/// Macro
@freestanding(expression)
public macro myMacro() = #externalMacro(module: "M", type: "T")

/// Top level async throws
public func run() async throws -> Int {
    return 0
}

/// Variadic and packs
public func pack<each T>(arg: repeat each T) {}

/// Private things
private class Internal {}
fileprivate func hidden() {}
"""
    source = SourceFile(path=Path("manager.swift"), language="swift", content=content)
    parser = SwiftParser(include_private=True)
    module = parser.parse(source)

    assert "Module documentation" in module.docstring

    # Protocol
    svc = next(c for c in module.classes if c.name == "Service")
    assert any(m.name == "id" and m.is_property for m in svc.methods)
    assert any(m.name == "start" and m.is_async and "throws" in m.return_type for m in svc.methods)

    # Extension for unknown
    ext_str = next(c for c in module.classes if c.name == "extension String")
    assert any(m.name == "localized" for m in ext_str.methods)

    # Macro
    macro = next(f for f in module.functions if f.name == "myMacro")
    assert "@macro" in macro.decorators

    # Pack - name might be different because of how I extract it
    pack_fn = next(f for f in module.functions if "pack" in f.name)
    assert len(pack_fn.parameters) == 1
    assert pack_fn.parameters[0].name == "arg"
    assert pack_fn.parameters[0].type_hint == "repeat each T"

    # Private
    assert any(c.name == "Internal" for c in module.classes)
    assert any(f.name == "hidden" for f in module.functions)


def test_swift_parser_private_filtered():
    content = "private func secret() {}"
    source = SourceFile(path=Path("main.swift"), language="swift", content=content)
    parser = SwiftParser(include_private=False)
    module = parser.parse(source)
    assert len(module.functions) == 0
