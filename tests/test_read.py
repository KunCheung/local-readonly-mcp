from pathlib import Path

from filesystem import ReadOnlyWorkspace


def test_reads_range_from_file_larger_than_direct_read_limit(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "large.log"
    target.write_text(
        "".join(f"line-{i}\n" for i in range(1, 10001)),
        encoding="utf-8",
    )

    workspace = ReadOnlyWorkspace(root, max_read_bytes=128)
    result = workspace.read_text_file("large.log", start_line=9000, end_line=9003)

    assert result["start_line"] == 9000
    assert result["end_line"] == 9003
    assert "9000 | line-9000" in result["content"]
    assert "9003 | line-9003" in result["content"]


def test_output_uses_compact_numbered_content(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = ReadOnlyWorkspace(root).read_text_file("a.txt")

    assert result["content"] == "1 | alpha\n2 | beta"
    assert "lines" not in result
