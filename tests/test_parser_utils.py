from llmstxt_gen.parsers.base import clean_docstring


def test_clean_javadoc():
    raw = """/**
 * This is a Javadoc.
 * It has multiple lines.
 */"""
    expected = "This is a Javadoc.\nIt has multiple lines."
    assert clean_docstring(raw) == expected

def test_clean_simple_block():
    raw = "/* Simple block */"
    assert clean_docstring(raw) == "Simple block"

def test_clean_triple_slash():
    raw = "/// Line 1\n/// Line 2"
    assert clean_docstring(raw) == "Line 1\nLine 2"

def test_clean_triple_slash_with_bang():
    raw = "//! Module doc\n//! Line 2"
    assert clean_docstring(raw) == "Module doc\nLine 2"

def test_clean_double_slash():
    raw = "// Simple comment\n// Another line"
    assert clean_docstring(raw) == "Simple comment\nAnother line"

def test_clean_hash_comment():
    raw = "# Ruby style\n# comment"
    assert clean_docstring(raw) == "Ruby style\ncomment"

def test_clean_leading_asterisks_no_markers():
    raw = " * Line 1\n * Line 2"
    assert clean_docstring(raw) == "Line 1\nLine 2"

def test_clean_mixed_whitespace():
    raw = "/** \n  *   Indent  \n  */"
    assert clean_docstring(raw) == "Indent"

def test_clean_empty():
    assert clean_docstring("") == ""
    assert clean_docstring(None) == ""
