from pathlib import Path

from filesystem import ReadOnlyWorkspace


def _make_files(root: Path, count: int = 12) -> None:
    for index in range(count):
        (root / f"file-{index:02d}.txt").write_text(
            f"needle value-{index}\n",
            encoding="utf-8",
        )


def test_list_directory_offset_limit_has_no_overlap(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _make_files(root)

    workspace = ReadOnlyWorkspace(root)
    page1 = workspace.list_directory(offset=0, limit=5)
    page2 = workspace.list_directory(offset=page1["next_offset"], limit=5)
    page3 = workspace.list_directory(offset=page2["next_offset"], limit=5)

    names1 = [item["name"] for item in page1["entries"]]
    names2 = [item["name"] for item in page2["entries"]]
    names3 = [item["name"] for item in page3["entries"]]

    assert page1["returned"] == 5
    assert page1["has_more"] is True
    assert page1["next_offset"] == 5
    assert page2["next_offset"] == 10
    assert page3["has_more"] is False
    assert page3["next_offset"] is None
    assert len(set(names1 + names2 + names3)) == 12


def test_search_files_offset_limit_has_no_overlap(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _make_files(root)

    workspace = ReadOnlyWorkspace(root)
    page1 = workspace.search_files("*.txt", offset=0, limit=4)
    page2 = workspace.search_files(
        "*.txt",
        offset=page1["next_offset"],
        limit=4,
    )

    paths1 = [item["path"] for item in page1["results"]]
    paths2 = [item["path"] for item in page2["results"]]

    assert page1["returned"] == 4
    assert page1["next_offset"] == 4
    assert set(paths1).isdisjoint(paths2)


def test_search_text_offset_limit_has_no_overlap(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _make_files(root)

    workspace = ReadOnlyWorkspace(root)
    page1 = workspace.search_text("needle", offset=0, limit=5)
    page2 = workspace.search_text(
        "needle",
        offset=page1["next_offset"],
        limit=5,
    )
    page3 = workspace.search_text(
        "needle",
        offset=page2["next_offset"],
        limit=5,
    )

    keys = [
        (item["path"], item["line"])
        for page in (page1, page2, page3)
        for item in page["results"]
    ]

    assert len(keys) == 12
    assert len(set(keys)) == 12
    assert page3["has_more"] is False
    assert page3["next_offset"] is None


def test_recursive_directory_pagination_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "b").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "b" / "z.txt").write_text("z", encoding="utf-8")
    (root / "a" / "x.txt").write_text("x", encoding="utf-8")

    workspace = ReadOnlyWorkspace(root)
    first = workspace.list_directory(recursive=True, max_depth=2, offset=0, limit=10)
    second = workspace.list_directory(recursive=True, max_depth=2, offset=0, limit=10)

    assert first["entries"] == second["entries"]
