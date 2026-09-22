from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from config import WorkspaceRegistry


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=False,
)


def build_server(registry: WorkspaceRegistry) -> MCPServer:
    mcp = MCPServer(
        "local-readonly-files",
        instructions=(
            "Thin read-only filesystem capabilities for an MCP host. "
            "The host decides which tools to call, in what order, and whether to continue "
            "pagination or line-range reads. Use root aliases and relative paths only. "
            "The server does not expose absolute local paths, filesystem mutation tools, "
            "or arbitrary command execution."
        ),
    )

    @mcp.tool(annotations=READ_ONLY)
    def list_roots() -> dict[str, Any]:
        """List available read-only root aliases without exposing local absolute paths."""
        return registry.public_info()

    @mcp.tool(annotations=READ_ONLY)
    def reload_config() -> dict[str, Any]:
        """Reload the local root allowlist and read policy from the config file."""
        registry.reload()
        return registry.public_info()

    @mcp.tool(annotations=READ_ONLY)
    def list_directory(
        root: str | None = None,
        path: str = "",
        recursive: bool = False,
        max_depth: int = 2,
        offset: int = 0,
        limit: int = 100,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        """List a bounded page of files/directories below one configured root alias."""
        alias, workspace = registry.get(root)
        result = workspace.list_directory(
            path,
            recursive=recursive,
            max_depth=max_depth,
            offset=offset,
            limit=limit,
            include_hidden=include_hidden,
        )
        result["root"] = alias
        return result

    @mcp.tool(annotations=READ_ONLY)
    def stat_path(path: str, root: str | None = None) -> dict[str, Any]:
        """Return metadata for a file or directory using only its relative path."""
        alias, workspace = registry.get(root)
        result = workspace.stat(path)
        result["root"] = alias
        return result

    @mcp.tool(annotations=READ_ONLY)
    def read_text_file(
        path: str,
        root: str | None = None,
        start_line: int = 1,
        end_line: int = 300,
        encoding: str = "auto",
    ) -> dict[str, Any]:
        """Read a bounded text line range and return next_start_line when more is available."""
        alias, workspace = registry.get(root)
        result = workspace.read_text_file(
            path,
            start_line=start_line,
            end_line=end_line,
            encoding=encoding,
        )
        result["root"] = alias
        return result

    @mcp.tool(annotations=READ_ONLY)
    def search_files(
        pattern: str,
        root: str | None = None,
        path: str = "",
        offset: int = 0,
        limit: int = 100,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        """Return a bounded page of files matching a glob pattern."""
        alias, workspace = registry.get(root)
        result = workspace.search_files(
            pattern,
            path=path,
            offset=offset,
            limit=limit,
            include_hidden=include_hidden,
        )
        result["root"] = alias
        return result

    @mcp.tool(annotations=READ_ONLY)
    def search_text(
        query: str,
        root: str | None = None,
        path: str = "",
        file_glob: str = "*",
        case_sensitive: bool = False,
        offset: int = 0,
        limit: int = 50,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        """Return a bounded page of literal text matches."""
        alias, workspace = registry.get(root)
        result = workspace.search_text(
            query,
            path=path,
            file_glob=file_glob,
            case_sensitive=case_sensitive,
            offset=offset,
            limit=limit,
            include_hidden=include_hidden,
        )
        result["root"] = alias
        return result

    return mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only MCP server for explicitly configured local directories."
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("READONLY_MCP_CONFIG", str(DEFAULT_CONFIG)),
        help="Path to the local JSON configuration file.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly permit binding Streamable HTTP to a non-loopback host.",
    )
    return parser.parse_args()


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "ip6-localhost"}:
        return True

    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def main() -> None:
    args = parse_args()

    if args.transport == "streamable-http":
        if not _is_loopback_host(args.host) and not args.allow_remote:
            raise SystemExit(
                "Refusing non-loopback HTTP bind. Use --allow-remote only when "
                "you have intentionally added authentication/network controls."
            )

    registry = WorkspaceRegistry(args.config)
    mcp = build_server(registry)

    if args.transport == "stdio":
        mcp.run()
        return

    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
