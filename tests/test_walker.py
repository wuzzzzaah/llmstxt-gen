from pathlib import Path

from llmstxt_gen.config import LlmsTxtConfig
from llmstxt_gen.walker import _load_gitignore, detect_language, walk_repository


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


def test_load_gitignore_no_file(tmp_path: Path) -> None:
    spec = _load_gitignore(tmp_path)
    assert not spec.match_file("any.log")
    assert not spec.match_file("src/main.py")


def test_load_gitignore_with_single_pattern(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.log")
    spec = _load_gitignore(tmp_path)
    assert spec.match_file("error.log")
    assert spec.match_file("logs/app.log")
    assert not spec.match_file("main.py")


def test_load_gitignore_with_multiple_patterns(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.log\nnode_modules/\n")
    spec = _load_gitignore(tmp_path)
    assert spec.match_file("error.log")
    assert spec.match_file("node_modules/pkg/index.js")
    assert not spec.match_file("src/main.py")
