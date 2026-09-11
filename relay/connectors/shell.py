"""Shell connector: lets the builder tier run commands (npm install, pytest, etc.),
gated by an allowlist and an optional per-command confirmation callback. This is the
one connector with real blast radius, so it defaults to strict."""

import shlex
import subprocess


class ShellPermissionError(Exception):
    pass


def is_allowed(cmd: str, allowed_commands: list) -> bool:
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return False
    if not parts:
        return False
    return parts[0] in allowed_commands


def run_command(cmd: str, cwd: str, allowed_commands: list, confirm_fn=None, timeout: int = 120) -> dict:
    """Raises ShellPermissionError if the command's binary isn't allowlisted.
    If confirm_fn is given and returns False, the command is skipped (not run)."""
    if not is_allowed(cmd, allowed_commands):
        raise ShellPermissionError(
            f"'{cmd}' was blocked: its command is not in allowed_shell_commands. "
            f"Add it to your config if you trust it."
        )
    if confirm_fn is not None and not confirm_fn(cmd):
        return {"cmd": cmd, "skipped": True}
    proc = subprocess.run(
        cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-5000:],
        "stderr": proc.stderr[-5000:],
    }
