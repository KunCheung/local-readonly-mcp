from pathlib import Path
from types import SimpleNamespace

import pytest

import filesystem
from filesystem import ReadOnlyWorkspace


def test_reparse_attribute_fallback_for_python_310_311(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "entry"
    path.mkdir()

    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    if hasattr(Path, "is_junction"):
        monkeypatch.setattr(Path, "is_junction", lambda self: False)

    monkeypatch.setattr(
        filesystem.os,
        "lstat",
        lambda _: SimpleNamespace(st_file_attributes=0x0400),
    )

    assert ReadOnlyWorkspace._is_link_like(path) is True


def test_recursive_search_skips_symlink_and_reports_it(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "hidden.txt").write_text("needle", encoding="utf-8")

    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are not available in this environment")

    workspace = ReadOnlyWorkspace(root)
    result = workspace.search_text("needle")

    assert result["results"] == []
    assert result["skipped_links"] >= 1
