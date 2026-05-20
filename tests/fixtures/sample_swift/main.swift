/// Module doc comment.
import Foundation

/// A sample protocol.
public protocol Greeter {
    /// Returns a greeting.
    func greet() -> String
}

/**
 * A sample class implementing Greeter.
 */
public class Person: Greeter {
    public let name: String
    private let secret: String = "42"

    public init(name: String) {
        self.name = name
    }

    public func greet() -> String {
        return "Hello, \(name)!"
    }
}

public struct Point {
    public var x: Double
    public var y: Double
}

public enum Direction {
    case north, south
    case east
    case west
}

@available(iOS 13.0, *)
public actor Counter {
    private var count = 0
    public func increment() {
        count += 1
    }
}

extension Person {
    public func sayGoodbye() {
        print("Goodbye!")
    }
}

/// A top-level function.
public func add(_ a: Int, _ b: Int) -> Int {
    return a + b
}

private func privateFunc() {}
