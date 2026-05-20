from pathlib import Path
from unittest.mock import patch

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.walker import _is_binary, detect_language, walk_repository


def test_detect_language_recognises_supported_extensions() -> None:
    assert detect_language(Path("a.py")) == "python"
    assert detect_language(Path("a.ts")) == "typescript"
    assert detect_language(Path("a.tsx")) == "typescript"
    assert detect_language(Path("a.js")) == "javascript"
    assert detect_language(Path("a.go")) == "go"
    assert detect_language(Path("a.txt")) is None


def test_walker_finds_python_fixture(sample_python_root: Path) -> None:
    cfg = LlmsTxtConfig(root=sample_python_root, languages=["python"], extensions=[".py"])
    files = list(walk_repository(cfg))
    names = {f.path.name for f in files}
    assert "calculator.py" in names
    assert all(f.language == "python" for f in files)


def test_walker_respects_exclude(sample_python_root: Path) -> None:
    cfg = LlmsTxtConfig(
        root=sample_python_root,
        languages=["python"],
        extensions=[".py"],
        exclude=["calculator.py"],
    )
    files = list(walk_repository(cfg))
    assert all(f.path.name != "calculator.py" for f in files)


def test_walker_finds_typescript_fixture(sample_typescript_root: Path) -> None:
    cfg = LlmsTxtConfig(
        root=sample_typescript_root,
        languages=["typescript"],
        extensions=[".ts"],
    )
    files = list(walk_repository(cfg))
    assert {f.path.name for f in files} == {"index.ts"}


def test_walker_finds_go_fixture(sample_go_root: Path) -> None:
    cfg = LlmsTxtConfig(
        root=sample_go_root,
        languages=["go"],
        extensions=[".go"],
    )
    files = list(walk_repository(cfg))
    assert {f.path.name for f in files} == {"main.go"}


def test_is_binary_handles_oserror() -> None:
    with patch("pathlib.Path.open", side_effect=OSError):
        assert _is_binary(Path("anyfile.py")) is True


def test_walker_skips_unreadable_files(tmp_path: Path) -> None:
    # Create a dummy project structure
    root = tmp_path / "project"
    root.mkdir()
    readable = root / "readable.py"
    readable.write_text("print('hello')")
    unreadable = root / "unreadable.py"
    unreadable.write_text("print('unreadable')")

    cfg = LlmsTxtConfig(root=root, languages=["python"], extensions=[".py"])

    original_open = Path.open

    def side_effect(path_obj: Path, *args: object, **kwargs: object) -> object:
        if path_obj.name == "unreadable.py":
            raise OSError("Unreadable file")
        return original_open(path_obj, *args, **kwargs)

    with patch("pathlib.Path.open", side_effect=side_effect, autospec=True):
        files = list(walk_repository(cfg))

    names = {f.path.name for f in files}
    assert "readable.py" in names
    assert "unreadable.py" not in names
