package com.example

/**
 * Main application object.
 */
object Main {
  /**
   * Entry point.
   */
  def main(args: Array[String]): Unit = {
    println("Hello, Scala!")
  }

  private def privateHelper(): Unit = ()
}

/**
 * A sample class with a companion object.
 */
class Greeter(val prefix: String) {
  def greet(name: String): String = s"$prefix, $name!"
}

object Greeter {
  def defaultPrefix = "Hello"
}

case class Person(name: String, age: Int = 30)

trait Flyable {
  def fly(): Unit
}

enum Color {
  case Red, Green, Blue
}

extension (s: String) {
  def shouting: String = s.toUpperCase
}

given intOrd: Ordering[Int] with {
  def compare(x: Int, y: Int) = x - y
}
