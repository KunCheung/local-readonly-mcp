from pathlib import Path

from filesystem import ReadOnlyWorkspace


def test_reads_requested_line_range(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "source.txt"
    target.write_text(
        "".join(f"line-{i}\n" for i in range(1, 1001)),
        encoding="utf-8",
    )

    result = ReadOnlyWorkspace(root).read_text_file(
        "source.txt",
        start_line=100,
        end_line=102,
    )

    assert result["start_line"] == 100
    assert result["end_line"] == 102
    assert "100 | line-100" in result["content"]
    assert "102 | line-102" in result["content"]
    assert result["has_more"] is True
    assert result["next_start_line"] == 103


def test_end_of_file_has_no_next_start_line(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = ReadOnlyWorkspace(root).read_text_file("a.txt")

    assert result["content"] == "1 | alpha\n2 | beta"
    assert result["has_more"] is False
    assert result["next_start_line"] is None


def test_output_budget_sets_next_start_line(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text(
        "".join(f"{'x' * 40}-{i}\n" for i in range(1, 20)),
        encoding="utf-8",
    )

    workspace = ReadOnlyWorkspace(root, max_output_chars=120)
    result = workspace.read_text_file("a.txt", start_line=1, end_line=19)

    assert result["has_more"] is True
    assert result["next_start_line"] == result["end_line"] + 1
    assert len(result["content"]) <= 120
