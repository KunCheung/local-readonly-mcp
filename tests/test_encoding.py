from pathlib import Path

from filesystem import ReadOnlyWorkspace


def test_reads_utf16_with_bom(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "windows.txt"
    target.write_text("第一行\n第二行\n", encoding="utf-16")

    result = ReadOnlyWorkspace(root).read_text_file("windows.txt")

    assert result["encoding"] == "utf-16"
    assert "1 | 第一行" in result["content"]
    assert "2 | 第二行" in result["content"]
