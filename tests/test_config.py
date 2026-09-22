import json
from pathlib import Path

import pytest

from config import WorkspaceRegistry
from filesystem import WorkspaceError


def test_public_info_hides_absolute_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"default_root": "work", "roots": {"work": str(root)}}),
        encoding="utf-8",
    )

    info = WorkspaceRegistry(config).public_info()
    rendered = json.dumps(info)

    assert str(root) not in rendered
    assert info["default_root"] == "work"
    assert info["roots"]["work"]["available"] is True


def test_failed_reload_keeps_previous_registry(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"default_root": "work", "roots": {"work": str(root)}}),
        encoding="utf-8",
    )

    registry = WorkspaceRegistry(config)
    config.write_text('{"roots": {}}', encoding="utf-8")

    with pytest.raises(WorkspaceError):
        registry.reload()

    assert registry.get("work")[0] == "work"
