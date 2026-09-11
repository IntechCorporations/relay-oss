"""Filesystem connector: gives the orchestrator a bounded view of a project directory
and a safe way to read/write files inside it."""

from pathlib import Path

DEFAULT_IGNORE = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".savr", ".relay", ".pytest_cache", ".mypy_cache", "target",
}


def list_tree(root: str, max_entries: int = 400, max_depth: int = 6) -> list:
    """Return a bounded, sorted listing of the project so a planner model can see
    the shape of the codebase without blowing the context window."""
    root_path = Path(root)
    entries = []
    for path in sorted(root_path.rglob("*")):
        rel = path.relative_to(root_path)
        if any(part in DEFAULT_IGNORE for part in rel.parts):
            continue
        if len(rel.parts) > max_depth:
            continue
        entries.append(str(rel) + ("/" if path.is_dir() else ""))
        if len(entries) >= max_entries:
            entries.append("... (truncated, project has more files)")
            break
    return entries


def read_file(root: str, rel_path: str, max_bytes: int = 200_000) -> str:
    """Returns '' for a file that doesn't exist yet — the builder tier treats that
    as 'create this file'."""
    p = Path(root) / rel_path
    if not p.exists() or not p.is_file():
        return ""
    data = p.read_bytes()[:max_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def write_file(root: str, rel_path: str, content: str) -> str:
    p = Path(root) / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)
