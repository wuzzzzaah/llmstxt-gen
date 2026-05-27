from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from llmstxt_gen.cli import app
from llmstxt_gen.parsers.base import ParsedModule

runner = CliRunner()


def test_watch_and_diff_incompatible(tmp_path):
    """Test that --watch and --diff cannot be used together."""
    result = runner.invoke(app, ["generate", str(tmp_path), "--watch", "--diff", "HEAD"])
    assert result.exit_code == 1
    assert "Error: --watch and --diff cannot be used together." in result.output


@patch("llmstxt_gen.cli.iter_changes")
@patch("llmstxt_gen.cli.write_outputs")
@patch("llmstxt_gen.cli._collect_modules")
def test_generate_watch_loop(mock_collect, mock_write, mock_iter, tmp_path):
    """Test the watch loop in the generate command."""
    # Create a dummy file to parse
    (tmp_path / "test.py").write_text("def hello(): pass")

    # Mock iter_changes to yield once then stop
    mock_iter.return_value = iter([{"test.py"}])

    # Mock _collect_modules to return something
    mock_module = ParsedModule(name="test", path="test.py", language="python")
    mock_collect.return_value = [mock_module]

    # Mock write_outputs to return paths
    mock_write.return_value = [Path("llms.txt")]

    result = runner.invoke(app, ["generate", str(tmp_path), "--watch"])

    assert result.exit_code == 0
    assert "Watching for changes" in result.output
    assert "Rebuilt in" in result.output

    # Initial call + 1 from watch loop
    assert mock_collect.call_count == 2
    assert mock_write.call_count == 2


@patch("llmstxt_gen.cli.iter_changes")
@patch("llmstxt_gen.cli._collect_modules")
def test_generate_watch_keyboard_interrupt(mock_collect, mock_iter, tmp_path):
    """Test that KeyboardInterrupt exits gracefully."""
    # Mock _collect_modules to avoid early exit if no files found
    mock_collect.return_value = [ParsedModule(name="test", path="test.py", language="python")]
    mock_iter.side_effect = KeyboardInterrupt()

    result = runner.invoke(app, ["generate", str(tmp_path), "--watch"])

    assert result.exit_code == 0
    assert "Watching stopped." in result.output
