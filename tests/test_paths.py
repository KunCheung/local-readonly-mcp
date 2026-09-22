from pathlib import Path

import pytest

from filesystem import ReadOnlyWorkspace, WorkspaceError


def test_blocks_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    workspace = ReadOnlyWorkspace(root)

    with pytest.raises(WorkspaceError):
        workspace.resolve("../outside/secret.txt")


def test_stat_does_not_expose_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")

    result = ReadOnlyWorkspace(root).stat("a.txt")

    assert result["path"] == "a.txt"
    assert "absolute_path" not in result
