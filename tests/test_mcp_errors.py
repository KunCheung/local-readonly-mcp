import json
from pathlib import Path

import pytest
from mcp import Client

from config import WorkspaceRegistry
from server import build_server


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_workspace_error_becomes_tool_error_result(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"roots": {"work": str(root)}}),
        encoding="utf-8",
    )

    mcp = build_server(WorkspaceRegistry(config_path))

    async with Client(mcp) as client:
        result = await client.call_tool(
            "read_text_file",
            {"root": "work", "path": "missing.txt"},
        )

    assert result.is_error is True
