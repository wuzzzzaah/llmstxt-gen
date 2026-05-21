from llmstxt_gen.cache import (
    deserialize_module,
    get_sha256,
    load_cache,
    save_cache,
    serialize_module,
)
from llmstxt_gen.parsers.base import ParsedFunction, ParsedModule, ParsedParameter


def test_get_sha256():
    content = "hello world"
    # echo -n "hello world" | sha256sum
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert get_sha256(content) == expected


def test_load_save_cache(tmp_path):
    cache_path = tmp_path / ".llmstxt_cache.json"
    data = {"file.py": {"hash": "abc", "module": {}}}

    # Test load missing
    assert load_cache(cache_path) == {}

    # Test save and load
    save_cache(cache_path, data)
    assert load_cache(cache_path) == data

    # Test corrupt cache
    cache_path.write_text("invalid json")
    assert load_cache(cache_path) == {}


def test_serialization_roundtrip():
    module = ParsedModule(
        name="test",
        path="test.py",
        language="python",
        docstring="module doc",
        functions=[
            ParsedFunction(
                name="func",
                parameters=[ParsedParameter(name="a", type_hint="int")],
                return_type="None",
                docstring="func doc",
                line=10,
                is_async=True,
            )
        ],
        env_vars={"KEY": ["test.py"]},
    )

    serialized = serialize_module(module)
    deserialized = deserialize_module(serialized)

    assert deserialized == module
    assert deserialized.functions[0].parameters[0].name == "a"
    assert deserialized.functions[0].is_async is True


def test_complex_serialization_roundtrip():
    from llmstxt_gen.parsers.base import ParsedClass, ParsedConstant, ParsedRoute

    module = ParsedModule(
        name="complex",
        path="complex.py",
        language="python",
        classes=[
            ParsedClass(
                name="Cls",
                docstring="cls doc",
                bases=["Base"],
                methods=[ParsedFunction(name="meth")],
                class_vars=[ParsedConstant(name="CV", value="1")],
                line=5,
            )
        ],
        constants=[ParsedConstant(name="CONST", value="2")],
        routes=[ParsedRoute(method="GET", path="/", handler="h")],
    )

    serialized = serialize_module(module)
    deserialized = deserialize_module(serialized)

    assert deserialized == module
    assert len(deserialized.classes) == 1
    assert deserialized.classes[0].methods[0].name == "meth"
    assert deserialized.classes[0].class_vars[0].name == "CV"
    assert deserialized.constants[0].name == "CONST"
    assert deserialized.routes[0].path == "/"


def test_cli_incremental(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from llmstxt_gen.cli import app

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test-incr"\nversion = "0.1.0"\n'
    )
    (tmp_path / "a.py").write_text("def a(): pass")

    runner = CliRunner()

    # First run: should parse and create cache
    result = runner.invoke(app, ["generate", str(tmp_path), "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    cache_file = tmp_path / ".llmstxt_cache.json"
    assert cache_file.exists()

    # Second run (incremental): should hit cache
    result = runner.invoke(
        app,
        ["generate", str(tmp_path), "--output-dir", str(tmp_path), "--incremental", "--verbose"],
    )
    assert result.exit_code == 0
    assert "cache hit: a.py" in result.stdout

    # Change file: should re-parse
    (tmp_path / "a.py").write_text("def a(): return 1")
    result = runner.invoke(
        app,
        ["generate", str(tmp_path), "--output-dir", str(tmp_path), "--incremental", "--verbose"],
    )
    assert result.exit_code == 0
    assert "parsed a.py" in result.stdout
    assert "cache hit: a.py" not in result.stdout

    # Stats command with incremental
    result = runner.invoke(app, ["stats", str(tmp_path), "--incremental"])
    assert result.exit_code == 0
