from pathlib import Path

from typer.testing import CliRunner

from codexa.cli import app

runner = CliRunner()


def test_generate_writes_files_for_python_fixture(tmp_path: Path, sample_python_root: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    for src in sample_python_root.iterdir():
        (target / src.name).write_text(src.read_text())

    result = runner.invoke(app, ["generate", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "llms.txt").is_file()
    assert (target / "llms-full.txt").is_file()


def test_generate_dry_run_prints_to_stdout(tmp_path: Path, sample_python_root: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    for src in sample_python_root.iterdir():
        (target / src.name).write_text(src.read_text())

    result = runner.invoke(app, ["generate", str(target), "--dry-run"])
    assert result.exit_code == 0
    assert "llms.txt" in result.output
    assert not (target / "llms.txt").exists()


def test_generate_exits_when_no_files_found(tmp_path: Path) -> None:
    result = runner.invoke(app, ["generate", str(tmp_path)])
    assert result.exit_code == 1


def test_validate_passes_on_generated_file(tmp_path: Path, sample_python_root: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    for src in sample_python_root.iterdir():
        (target / src.name).write_text(src.read_text())
    runner.invoke(app, ["generate", str(target)])

    result = runner.invoke(app, ["validate", str(target / "llms.txt")])
    assert result.exit_code == 0


def test_validate_fails_on_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "missing.txt")])
    assert result.exit_code == 1


def test_validate_fails_on_invalid_content(tmp_path: Path) -> None:
    bad = tmp_path / "llms.txt"
    bad.write_text("not a heading")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1


def test_stats_reports_counts(tmp_path: Path, sample_python_root: Path) -> None:
    target = tmp_path / "p"
    target.mkdir()
    for src in sample_python_root.iterdir():
        (target / src.name).write_text(src.read_text())

    result = runner.invoke(app, ["stats", str(target)])
    assert result.exit_code == 0
    assert "functions" in result.output
    assert "classes" in result.output
