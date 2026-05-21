import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from llmstxt_gen.cli import app
from llmstxt_gen.diff import GitError, get_changed_files

runner = CliRunner()


def test_get_changed_files_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "file1.py\nfile2.ts\n"

    with patch("subprocess.run", return_value=mock_result):
        changed = get_changed_files("HEAD", Path("."))
        assert changed == {"file1.py", "file2.ts"}


def test_get_changed_files_git_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(GitError, match="git command not found"):
            get_changed_files("HEAD", Path("."))


def test_get_changed_files_invalid_ref():
    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stderr = "fatal: ambiguous argument 'invalid-ref': unknown revision or path not in the working tree."

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(GitError, match="git diff failed"):
            get_changed_files("invalid-ref", Path("."))


def test_cli_diff_mode_no_changes(tmp_path):
    # Create a dummy file so _collect_modules has something to scan
    (tmp_path / "test.py").write_text("def hello(): pass")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""  # No changes

    with patch("subprocess.run", return_value=mock_result):
        result = runner.invoke(app, ["generate", str(tmp_path), "--diff"])
        print(f"OUTPUT: {result.output}")
        print(f"EXIT CODE: {result.exit_code}")
        # Typer might exit with 1 if we raise typer.Exit(code=1)
        assert result.exit_code == 1
        assert "No changed files found for ref 'HEAD'" in result.output


def test_cli_diff_mode_success(tmp_path):
    (tmp_path / "test.py").write_text("def hello(): pass")

    mock_diff = MagicMock()
    mock_diff.returncode = 0
    mock_diff.stdout = "test.py\n"

    with patch("subprocess.run", return_value=mock_diff):
        result = runner.invoke(app, ["generate", str(tmp_path), "--diff", "main", "--dry-run"])
        assert result.exit_code == 0
        assert "===== llms-diff.txt =====" in result.output
        assert "## test.py" in result.output
        assert "Partial view" in result.output


def test_cli_diff_invalid_ref(tmp_path):
    (tmp_path / "test.py").write_text("def hello(): pass")

    mock_diff = MagicMock()
    mock_diff.returncode = 128
    mock_diff.stderr = "fatal: bad revision"

    with patch("subprocess.run", return_value=mock_diff):
        result = runner.invoke(app, ["generate", str(tmp_path), "--diff", "invalid"])
        assert result.exit_code == 1
        assert "Error: git diff failed: fatal: bad revision" in result.output
