from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Iterator

from mcp.server import MCPServer
from mcp.types import ToolAnnotations


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_MAX_READ_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_SEARCH_FILE_BYTES = 10 * 1024 * 1024
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

SKIP_DIR_NAMES = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
}

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)


class WorkspaceError(ValueError):
    """Raised when a requested path or workspace configuration is unsafe."""


class ReadOnlyWorkspace:
    def __init__(
        self,
        root: str | Path,
        *,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_search_file_bytes: int = DEFAULT_MAX_SEARCH_FILE_BYTES,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)
        self.max_read_bytes = int(max_read_bytes)
        self.max_search_file_bytes = int(max_search_file_bytes)

    def _check_root(self) -> None:
        if not self.root.exists():
            raise WorkspaceError(f"Configured root does not exist: {self.root}")
        if not self.root.is_dir():
            raise WorkspaceError(f"Configured root is not a directory: {self.root}")

    def resolve(self, user_path: str = "") -> Path:
        """Resolve a path and guarantee it remains inside this workspace."""
        self._check_root()
        raw = (user_path or "").strip()
        candidate = Path(raw) if raw else self.root

        if not candidate.is_absolute():
            candidate = self.root / candidate

        resolved = candidate.expanduser().resolve(strict=True)

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(
                f"Access denied: path escapes configured root {self.root}"
            ) from exc

        return resolved

    def relative(self, path: Path) -> str:
        return "." if path == self.root else path.relative_to(self.root).as_posix()

    @staticmethod
    def _looks_binary(data: bytes) -> bool:
        if b"\x00" in data:
            return True
        if not data:
            return False
        control = sum(1 for byte in data if byte < 9 or 13 < byte < 32)
        return control / len(data) > 0.10

    @staticmethod
    def _decode(data: bytes, encoding: str = "auto") -> tuple[str, str]:
        if encoding != "auto":
            try:
                return data.decode(encoding), encoding
            except (LookupError, UnicodeDecodeError) as exc:
                raise WorkspaceError(f"Unable to decode with encoding={encoding!r}") from exc

        for candidate in TEXT_ENCODINGS:
            try:
                return data.decode(candidate), candidate
            except UnicodeDecodeError:
                pass

        raise WorkspaceError("Unsupported text encoding or binary file")

    def _safe_dirs(
        self,
        current: Path,
        dirs: list[str],
        *,
        include_hidden: bool,
    ) -> list[str]:
        safe: list[str] = []
        for name in dirs:
            if not include_hidden and name.startswith("."):
                continue
            if name in SKIP_DIR_NAMES:
                continue

            child = current / name
            try:
                resolved = child.resolve(strict=True)
                resolved.relative_to(self.root)
            except (OSError, ValueError):
                continue

            if child.is_symlink():
                continue

            safe.append(name)

        return safe

    def iter_files(
        self,
        base: Path,
        *,
        include_hidden: bool = False,
    ) -> Iterator[Path]:
        if base.is_file():
            yield base
            return

        for current_str, dirs, files in os.walk(base, followlinks=False):
            current = Path(current_str)
            dirs[:] = self._safe_dirs(
                current,
                dirs,
                include_hidden=include_hidden,
            )

            for name in files:
                if not include_hidden and name.startswith("."):
                    continue

                path = current / name
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(self.root)
                except (OSError, ValueError):
                    continue

                if resolved.is_file():
                    yield resolved

    def stat(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        stat = target.stat()
        return {
            "path": self.relative(target),
            "absolute_path": str(target),
            "type": "directory" if target.is_dir() else "file",
            "size_bytes": stat.st_size,
            "modified_time_unix": stat.st_mtime,
            "is_symlink": target.is_symlink(),
        }

    def list_directory(
        self,
        path: str = "",
        *,
        recursive: bool = False,
        max_depth: int = 2,
        max_entries: int = 200,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        target = self.resolve(path)
        if not target.is_dir():
            raise WorkspaceError(f"Not a directory: {self.relative(target)}")

        max_depth = max(0, min(int(max_depth), 10))
        max_entries = max(1, min(int(max_entries), 2000))
        entries: list[dict[str, Any]] = []
        truncated = False

        def append_entry(path_obj: Path) -> bool:
            nonlocal truncated
            if len(entries) >= max_entries:
                truncated = True
                return False

            try:
                resolved = path_obj.resolve(strict=True)
                resolved.relative_to(self.root)
                stat = resolved.stat()
            except (OSError, ValueError):
                return True

            entries.append(
                {
                    "path": self.relative(resolved),
                    "name": path_obj.name,
                    "type": "directory" if resolved.is_dir() else "file",
                    "size_bytes": stat.st_size if resolved.is_file() else None,
                }
            )
            return True

        if not recursive:
            children = sorted(
                target.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
            for child in children:
                if not include_hidden and child.name.startswith("."):
                    continue
                if not append_entry(child):
                    break
        else:
            base_depth = len(target.parts)
            for current_str, dirs, files in os.walk(target, followlinks=False):
                current = Path(current_str)
                depth = len(current.parts) - base_depth
                dirs[:] = self._safe_dirs(
                    current,
                    dirs,
                    include_hidden=include_hidden,
                )
                if depth >= max_depth:
                    dirs[:] = []

                for name in sorted([*dirs, *files], key=str.lower):
                    if not include_hidden and name.startswith("."):
                        continue
                    if not append_entry(current / name):
                        break

                if truncated:
                    break

        return {
            "directory": self.relative(target),
            "count": len(entries),
            "truncated": truncated,
            "entries": entries,
        }

    def read_text_file(
        self,
        path: str,
        *,
        start_line: int = 1,
        end_line: int = 400,
        encoding: str = "auto",
    ) -> dict[str, Any]:
        target = self.resolve(path)
        if not target.is_file():
            raise WorkspaceError(f"Not a file: {self.relative(target)}")

        size = target.stat().st_size
        if size > self.max_read_bytes:
            raise WorkspaceError(
                f"File is {size} bytes; direct-read limit is {self.max_read_bytes}. "
                "Use search_text() to locate relevant lines."
            )

        data = target.read_bytes()
        if self._looks_binary(data[:8192]):
            raise WorkspaceError("Binary file detected")

        text, used_encoding = self._decode(data, encoding)
        lines = text.splitlines()

        start = max(1, int(start_line))
        requested_end = max(start, int(end_line))
        end = min(requested_end, start + 1999)
        selected = lines[start - 1 : end]

        return {
            "path": self.relative(target),
            "encoding": used_encoding,
            "size_bytes": size,
            "total_lines": len(lines),
            "start_line": start,
            "end_line": start + len(selected) - 1 if selected else start - 1,
            "truncated": end < len(lines),
            "lines": [
                {"line": start + index, "text": line}
                for index, line in enumerate(selected)
            ],
        }

    def search_files(
        self,
        pattern: str,
        *,
        path: str = "",
        max_results: int = 100,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        base = self.resolve(path)
        if not base.is_dir():
            raise WorkspaceError(f"Not a directory: {self.relative(base)}")

        limit = max(1, min(int(max_results), 1000))
        needle = pattern.lower()
        results: list[dict[str, Any]] = []

        for file_path in self.iter_files(base, include_hidden=include_hidden):
            relative = self.relative(file_path)
            if fnmatch.fnmatch(file_path.name.lower(), needle) or fnmatch.fnmatch(
                relative.lower(), needle
            ):
                results.append(
                    {
                        "path": relative,
                        "size_bytes": file_path.stat().st_size,
                    }
                )
                if len(results) >= limit:
                    return {
                        "pattern": pattern,
                        "count": len(results),
                        "truncated": True,
                        "results": results,
                    }

        return {
            "pattern": pattern,
            "count": len(results),
            "truncated": False,
            "results": results,
        }

    def search_text(
        self,
        query: str,
        *,
        path: str = "",
        file_glob: str = "*",
        case_sensitive: bool = False,
        max_results: int = 100,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        if not query:
            raise WorkspaceError("query must not be empty")

        base = self.resolve(path)
        limit = max(1, min(int(max_results), 1000))
        needle = query if case_sensitive else query.lower()
        results: list[dict[str, Any]] = []
        skipped_binary = 0
        skipped_large = 0

        for file_path in self.iter_files(base, include_hidden=include_hidden):
            if not fnmatch.fnmatch(file_path.name.lower(), file_glob.lower()):
                continue

            try:
                size = file_path.stat().st_size
                if size > self.max_search_file_bytes:
                    skipped_large += 1
                    continue

                with file_path.open("rb") as stream:
                    prefix = stream.read(8192)

                if self._looks_binary(prefix):
                    skipped_binary += 1
                    continue

                data = file_path.read_bytes()
                try:
                    text, used_encoding = self._decode(data)
                except WorkspaceError:
                    skipped_binary += 1
                    continue

                for line_number, line in enumerate(text.splitlines(), start=1):
                    haystack = line if case_sensitive else line.lower()
                    if needle in haystack:
                        results.append(
                            {
                                "path": self.relative(file_path),
                                "line": line_number,
                                "text": line[:2000],
                                "encoding": used_encoding,
                            }
                        )
                        if len(results) >= limit:
                            return {
                                "query": query,
                                "file_glob": file_glob,
                                "count": len(results),
                                "truncated": True,
                                "skipped_binary": skipped_binary,
                                "skipped_large": skipped_large,
                                "results": results,
                            }
            except (OSError, PermissionError):
                continue

        return {
            "query": query,
            "file_glob": file_glob,
            "count": len(results),
            "truncated": False,
            "skipped_binary": skipped_binary,
            "skipped_large": skipped_large,
            "results": results,
        }


class WorkspaceRegistry:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).expanduser().resolve(strict=False)
        self.workspaces: dict[str, ReadOnlyWorkspace] = {}
        self.default_root: str = ""
        self.reload()

    def reload(self) -> None:
        if not self.config_path.exists():
            raise WorkspaceError(f"Config file does not exist: {self.config_path}")

        config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        roots = config.get("roots")

        if not isinstance(roots, dict) or not roots:
            raise WorkspaceError("config.json must contain a non-empty 'roots' object")

        global_read_limit = int(
            config.get("max_read_bytes", DEFAULT_MAX_READ_BYTES)
        )
        global_search_limit = int(
            config.get("max_search_file_bytes", DEFAULT_MAX_SEARCH_FILE_BYTES)
        )

        workspaces: dict[str, ReadOnlyWorkspace] = {}

        for alias, value in roots.items():
            if isinstance(value, str):
                root_path = value
                read_limit = global_read_limit
                search_limit = global_search_limit
            elif isinstance(value, dict):
                root_path = value.get("path")
                read_limit = int(
                    value.get("max_read_bytes", global_read_limit)
                )
                search_limit = int(
                    value.get("max_search_file_bytes", global_search_limit)
                )
            else:
                raise WorkspaceError(
                    f"Invalid config for root {alias!r}: expected string or object"
                )

            if not root_path:
                raise WorkspaceError(f"Root {alias!r} has no path")

            workspaces[alias] = ReadOnlyWorkspace(
                root_path,
                max_read_bytes=read_limit,
                max_search_file_bytes=search_limit,
            )

        default_root = config.get("default_root") or next(iter(workspaces))
        if default_root not in workspaces:
            raise WorkspaceError(
                f"default_root={default_root!r} is not present in roots"
            )

        self.workspaces = workspaces
        self.default_root = default_root

    def get(self, alias: str | None = None) -> tuple[str, ReadOnlyWorkspace]:
        selected = alias or self.default_root
        workspace = self.workspaces.get(selected)
        if workspace is None:
            raise WorkspaceError(
                f"Unknown root {selected!r}; available: {', '.join(self.workspaces)}"
            )
        return selected, workspace

    def info(self) -> dict[str, Any]:
        return {
            "mode": "read-only",
            "config_path": str(self.config_path),
            "default_root": self.default_root,
            "roots": {
                alias: {
                    "path": str(workspace.root),
                    "exists": workspace.root.exists() and workspace.root.is_dir(),
                    "max_read_bytes": workspace.max_read_bytes,
                    "max_search_file_bytes": workspace.max_search_file_bytes,
                }
                for alias, workspace in self.workspaces.items()
            },
        }


CONFIG_PATH = Path(
    os.environ.get("READONLY_MCP_CONFIG", str(DEFAULT_CONFIG))
).expanduser()
registry = WorkspaceRegistry(CONFIG_PATH)

mcp = MCPServer(
    "local-readonly-files",
    instructions=(
        "Read-only access to explicitly configured local filesystem roots. "
        "This server provides no write, edit, delete, rename, copy, mkdir, "
        "shell, package-install, or arbitrary command-execution tools."
    ),
)


@mcp.tool(annotations=READ_ONLY)
def list_roots() -> dict[str, Any]:
    """List configured read-only roots and their aliases."""
    return registry.info()


@mcp.tool(annotations=READ_ONLY)
def reload_config() -> dict[str, Any]:
    """Reload the local read-only root configuration from disk."""
    registry.reload()
    return registry.info()


@mcp.tool(annotations=READ_ONLY)
def list_directory(
    root: str | None = None,
    path: str = "",
    recursive: bool = False,
    max_depth: int = 2,
    max_entries: int = 200,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """List files/directories below one configured root."""
    alias, workspace = registry.get(root)
    result = workspace.list_directory(
        path,
        recursive=recursive,
        max_depth=max_depth,
        max_entries=max_entries,
        include_hidden=include_hidden,
    )
    result["root"] = alias
    return result


@mcp.tool(annotations=READ_ONLY)
def stat_path(path: str, root: str | None = None) -> dict[str, Any]:
    """Return read-only metadata for a file or directory."""
    alias, workspace = registry.get(root)
    result = workspace.stat(path)
    result["root"] = alias
    return result


@mcp.tool(annotations=READ_ONLY)
def read_text_file(
    path: str,
    root: str | None = None,
    start_line: int = 1,
    end_line: int = 400,
    encoding: str = "auto",
) -> dict[str, Any]:
    """Read a bounded line range from a text file."""
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
    max_results: int = 100,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Recursively find files by glob pattern."""
    alias, workspace = registry.get(root)
    result = workspace.search_files(
        pattern,
        path=path,
        max_results=max_results,
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
    max_results: int = 100,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Recursively search literal text and return matching lines."""
    alias, workspace = registry.get(root)
    result = workspace.search_text(
        query,
        path=path,
        file_glob=file_glob,
        case_sensitive=case_sensitive,
        max_results=max_results,
        include_hidden=include_hidden,
    )
    result["root"] = alias
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only MCP server for configured local directories."
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

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
