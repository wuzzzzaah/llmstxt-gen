import tree_sitter_scala
from tree_sitter import Language, Parser

SCALA_LANGUAGE = Language(tree_sitter_scala.language())
parser = Parser(SCALA_LANGUAGE)

source = b"""
/**
 * A sample class
 */
class MyClass(val x: Int) extends Base {
  /** A method */
  def myMethod(y: String): Int = 42
}

object MyClass {
  def staticMethod(): Unit = ()
}
"""

tree = parser.parse(source)
root = tree.root_node

def print_tree(node, depth=0):
    print("  " * depth + f"{node.type}: {source[node.start_byte:node.end_byte].decode('utf-8').splitlines()[0]}")
    for child in node.children:
        print_tree(child, depth + 1)

print_tree(root)
