from pathlib import Path

import pytest

from filesystem import ReadOnlyWorkspace, WorkspaceError


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        "app/.env",
        "private.pem",
        "keys/private.key",
        "credentials.json",
        ".ssh/id_rsa",
    ],
)
def test_sensitive_files_are_blocked_by_default(
    tmp_path: Path,
    relative_path: str,
) -> None:
    root = tmp_path / "root"
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("secret", encoding="utf-8")

    workspace = ReadOnlyWorkspace(root)

    with pytest.raises(WorkspaceError):
        workspace.resolve(relative_path)


def test_env_example_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env.example").write_text("API_KEY=example", encoding="utf-8")

    workspace = ReadOnlyWorkspace(root)
    result = workspace.read_text_file(".env.example")

    assert "API_KEY=example" in result["content"]


def test_sensitive_filter_can_be_explicitly_disabled(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("A=B", encoding="utf-8")

    workspace = ReadOnlyWorkspace(root, allow_sensitive_files=True)
    result = workspace.read_text_file(".env")

    assert "A=B" in result["content"]
