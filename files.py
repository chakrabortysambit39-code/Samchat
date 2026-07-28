"""
files.py
Basic, guarded file-system operations. Deletion requires explicit
confirm=True so a misheard voice command can never wipe something.
"""
import os
import subprocess
import sys

from utils import get_logger

log = get_logger("files")


def list_dir(path: str = ".") -> list:
    path = os.path.expanduser(path)
    try:
        return sorted(os.listdir(path))
    except OSError as e:
        log.warning("list_dir failed: %s", e)
        return []


def search_files(name_fragment: str, root: str = "~") -> list:
    """Search for files whose name contains name_fragment (case-insensitive)."""
    root = os.path.expanduser(root)
    matches = []
    fragment = name_fragment.lower()
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden / system-y directories to keep this fast and sane
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if fragment in fname.lower():
                matches.append(os.path.join(dirpath, fname))
        if len(matches) >= 50:
            break
    return matches


def open_path(path: str) -> str:
    """Open a file or folder with the OS default application."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"'{path}' doesn't exist."
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: F821 (Windows only)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return f"Opening {path}."
    except Exception as e:
        log.warning("open_path failed: %s", e)
        return f"I couldn't open {path}."


def create_text_file(path: str, content: str = "") -> str:
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Created {path}."
    except OSError as e:
        log.warning("create_text_file failed: %s", e)
        return f"I couldn't create {path}."


def delete_path(path: str, confirm: bool = False) -> str:
    path = os.path.expanduser(path)
    if not confirm:
        return f"Please confirm before I delete {path}."
    if not os.path.exists(path):
        return f"'{path}' doesn't exist."
    try:
        if os.path.isdir(path):
            os.rmdir(path)  # only removes empty dirs — deliberately conservative
        else:
            os.remove(path)
        return f"Deleted {path}."
    except OSError as e:
        log.warning("delete_path failed: %s", e)
        return f"I couldn't delete {path}: {e}"
