from pathlib import Path

from codexa.config import CodexaConfig
from codexa.walker import detect_language, walk_repository


def test_detect_language_recognises_supported_extensions() -> None:
    assert detect_language(Path("a.py")) == "python"
    assert detect_language(Path("a.ts")) == "typescript"
    assert detect_language(Path("a.tsx")) == "typescript"
    assert detect_language(Path("a.js")) == "javascript"
    assert detect_language(Path("a.txt")) is None


def test_walker_finds_python_fixture(sample_python_root: Path) -> None:
    cfg = CodexaConfig(root=sample_python_root, languages=["python"], extensions=[".py"])
    files = list(walk_repository(cfg))
    names = {f.path.name for f in files}
    assert "calculator.py" in names
    assert all(f.language == "python" for f in files)


def test_walker_respects_exclude(sample_python_root: Path) -> None:
    cfg = CodexaConfig(
        root=sample_python_root,
        languages=["python"],
        extensions=[".py"],
        exclude=["calculator.py"],
    )
    files = list(walk_repository(cfg))
    assert all(f.path.name != "calculator.py" for f in files)


def test_walker_finds_typescript_fixture(sample_typescript_root: Path) -> None:
    cfg = CodexaConfig(
        root=sample_typescript_root,
        languages=["typescript"],
        extensions=[".ts"],
    )
    files = list(walk_repository(cfg))
    assert {f.path.name for f in files} == {"index.ts"}
