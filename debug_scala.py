import tree_sitter_scala
from tree_sitter import Language, Parser

SCALA_LANGUAGE = Language(tree_sitter_scala.language())
parser = Parser(SCALA_LANGUAGE)

source = b"""
package test

class TestClass(val x: Int)
"""

tree = parser.parse(source)
root = tree.root_node

def print_tree(node, depth=0):
    print("  " * depth + f"{node.type} ({node.named_child_count} named children): {source[node.start_byte:node.end_byte].decode('utf-8').splitlines()[0]}")
    for child in node.children:
        print_tree(child, depth + 1)

print_tree(root)
