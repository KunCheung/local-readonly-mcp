import json
import tempfile
from pathlib import Path

from server import ReadOnlyWorkspace, WorkspaceError, WorkspaceRegistry


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        root_a = base / "root-a"
        root_b = base / "root-b"
        root_a.mkdir()
        root_b.mkdir()

        (root_a / "hello.txt").write_text("hello\nworld\n", encoding="utf-8")
        (root_b / "other.txt").write_text("another root\n", encoding="utf-8")

        config_path = base / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_root": "a",
                    "roots": {
                        "a": str(root_a),
                        "b": str(root_b),
                    },
                }
            ),
            encoding="utf-8",
        )

        registry = WorkspaceRegistry(config_path)

        alias, workspace_a = registry.get()
        assert alias == "a"
        assert workspace_a.read_text_file("hello.txt")["lines"][0]["text"] == "hello"
        assert workspace_a.search_text("world")["count"] == 1
        assert workspace_a.search_files("*.txt")["count"] == 1

        alias, workspace_b = registry.get("b")
        assert alias == "b"
        assert workspace_b.search_files("*.txt")["count"] == 1

        try:
            workspace_a.resolve("../root-b/other.txt")
        except WorkspaceError:
            pass
        else:
            raise AssertionError("Cross-root traversal should be blocked")

        print("Configuration and path-boundary tests passed.")


if __name__ == "__main__":
    main()
