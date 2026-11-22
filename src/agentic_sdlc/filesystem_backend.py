"""Filesystem backend compatibility for contained Windows workspaces."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _without_extended_prefix(value: str) -> str:
    if value.startswith("\\\\?\\UNC\\"):
        return f"\\\\{value[8:]}"
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def _canonical(path: str | Path) -> Path:
    plain = _without_extended_prefix(str(path))
    resolved = os.path.realpath(os.path.abspath(plain))
    return Path(_without_extended_prefix(resolved))


def _is_host_absolute(value: str) -> bool:
    return bool(
        WINDOWS_DRIVE_PATH.match(value) or value.startswith("\\\\?\\") or value.startswith("\\\\")
    )


def _contained(candidate: Path, root: Path) -> bool:
    try:
        common = os.path.commonpath([os.path.normcase(str(candidate)), os.path.normcase(str(root))])
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(str(root))


def create_workspace_backend(root_dir: Path) -> Any:
    """Create a virtual filesystem backend tolerant of Windows extended paths.

    Deep Agents can surface extended-length paths on Windows. Feeding one back into the
    stock virtual backend compares it against a non-prefixed root and rejects it. This subclass
    canonicalizes both sides while retaining the same root-containment check.
    """
    from deepagents.backends import FilesystemBackend

    class WindowsCompatibleFilesystemBackend(FilesystemBackend):
        def __init__(self, root: Path) -> None:
            super().__init__(root_dir=root, virtual_mode=True)
            self.cwd = _canonical(self.cwd)

        def _resolve_path(self, key: str) -> Path:
            raw = _without_extended_prefix(key)
            root = _canonical(self.cwd)
            if _is_host_absolute(raw):
                candidate = _canonical(raw)
            else:
                virtual = raw.replace("\\", "/")
                parts = PurePosixPath(f"/{virtual.lstrip('/')}").parts[1:]
                if ".." in parts or "~" in parts:
                    raise ValueError("Path traversal not allowed")
                candidate = _canonical(root.joinpath(*parts))
            if not _contained(candidate, root):
                raise ValueError(f"Path:{candidate} outside root directory: {root}")
            return candidate

        def _to_virtual_path(self, path: Path) -> str:
            candidate = _canonical(path)
            root = _canonical(self.cwd)
            if not _contained(candidate, root):
                raise ValueError(f"Path:{candidate} outside root directory: {root}")
            relative = os.path.relpath(candidate, root).replace("\\", "/")
            return "/" if relative == "." else f"/{relative}"

    return WindowsCompatibleFilesystemBackend(root_dir)
