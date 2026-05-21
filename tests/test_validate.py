from pathlib import Path

from typer.testing import CliRunner

from llmstxt_gen.cli import app

runner = CliRunner()

def test_validate_success(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text("# Project\n\n> Description\n\n## Section\n- [Link](https://example.com)")
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 0
    assert "valid:" in result.output

def test_validate_missing_h1(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text("> Description\n\n## Section")
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 1
    assert "missing top-level H1 heading" in result.output

def test_validate_misplaced_blockquote(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text("# Project\n\n## Section\n\n> Misplaced")
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 1
    assert "blockquote must immediately follow H1 heading" in result.output

def test_validate_no_sections(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text("# Project\n\n> Description\n\nJust text, no sections.")
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 1
    assert "no '##' section found" in result.output

def test_validate_invalid_links(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text("# Project\n\n## Section\n- [](url)\n- [label]()")
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 1
    assert "empty link label" in result.output
    assert "empty link URL" in result.output

def test_validate_duplicate_anchors(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text('# Project\n\n## Section\n<a id="foo"></a>\n<a id="foo"></a>')
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 1
    assert "duplicate anchor 'foo'" in result.output

def test_validate_empty_file(tmp_path: Path):
    llms = tmp_path / "llms.txt"
    llms.write_text("   \n\n  ")
    result = runner.invoke(app, ["validate", str(llms)])
    assert result.exit_code == 1
    assert "is empty" in result.output

def test_validate_default_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    llms = tmp_path / "llms.txt"
    llms.write_text("# Project\n\n## Section")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert "valid: llms.txt" in result.output
