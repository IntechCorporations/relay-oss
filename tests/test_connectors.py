import tempfile

import pytest

from relay.connectors import filesystem, shell


def test_filesystem_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        filesystem.write_file(tmp, "a/b.txt", "hi")
        assert filesystem.read_file(tmp, "a/b.txt") == "hi"
        tree = filesystem.list_tree(tmp)
        assert any("b.txt" in entry for entry in tree)


def test_read_missing_file_returns_empty_string():
    with tempfile.TemporaryDirectory() as tmp:
        assert filesystem.read_file(tmp, "nope.txt") == ""


def test_shell_blocks_disallowed_command():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(shell.ShellPermissionError):
            shell.run_command("rm -rf /", cwd=tmp, allowed_commands=["ls"])


def test_shell_allows_listed_command():
    with tempfile.TemporaryDirectory() as tmp:
        result = shell.run_command("ls", cwd=tmp, allowed_commands=["ls"])
        assert result["returncode"] == 0


def test_shell_confirm_fn_can_skip():
    with tempfile.TemporaryDirectory() as tmp:
        result = shell.run_command(
            "ls", cwd=tmp, allowed_commands=["ls"], confirm_fn=lambda cmd: False
        )
        assert result["skipped"] is True
