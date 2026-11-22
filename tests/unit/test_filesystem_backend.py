from pathlib import Path

import pytest

from agentic_sdlc.filesystem_backend import create_workspace_backend


def extended(path: Path) -> str:
    return f"\\\\?\\{path}"


def test_extended_windows_path_inside_root_is_accepted(tmp_path: Path) -> None:
    root = tmp_path / "project"
    target = root / "tests" / "test_auth.py"
    target.parent.mkdir(parents=True)
    target.write_text("", encoding="utf-8")
    backend = create_workspace_backend(root)

    resolved = backend._resolve_path(extended(target))

    assert resolved == target.resolve()
    assert backend._to_virtual_path(Path(extended(target))) == "/tests/test_auth.py"


def test_extended_windows_path_outside_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("", encoding="utf-8")
    backend = create_workspace_backend(root)

    with pytest.raises(ValueError, match="outside root"):
        backend._resolve_path(extended(outside))


def test_virtual_path_and_traversal_rules_are_preserved(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    backend = create_workspace_backend(root)

    assert backend._resolve_path("/docs/PRD.md") == root / "docs" / "PRD.md"
    with pytest.raises(ValueError, match="traversal"):
        backend._resolve_path("/../secret.txt")
