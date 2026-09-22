from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from filesystem import (
    DEFAULT_ALLOW_PATTERNS,
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_MAX_READ_BYTES,
    DEFAULT_MAX_SEARCH_FILE_BYTES,
    ReadOnlyWorkspace,
    WorkspaceError,
)


class WorkspaceRegistry:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path).expanduser().resolve(strict=False)
        self.workspaces: dict[str, ReadOnlyWorkspace] = {}
        self.default_root = ""
        self.reload()

    def reload(self) -> None:
        if not self.config_path.exists():
            raise WorkspaceError(
                "Config file does not exist. Copy config.example.json to config.json first."
            )

        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError("Unable to read valid JSON configuration") from exc

        roots = config.get("roots")
        if not isinstance(roots, dict) or not roots:
            raise WorkspaceError("config must contain a non-empty 'roots' object")

        global_read_limit = int(
            config.get("max_read_bytes", DEFAULT_MAX_READ_BYTES)
        )
        global_search_limit = int(
            config.get("max_search_file_bytes", DEFAULT_MAX_SEARCH_FILE_BYTES)
        )
        global_output_limit = int(
            config.get("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS)
        )
        global_deny_patterns = tuple(config.get("deny_patterns", ()))
        global_allow_patterns = (
            DEFAULT_ALLOW_PATTERNS + tuple(config.get("allow_patterns", ()))
        )
        global_allow_sensitive = bool(config.get("allow_sensitive_files", False))

        workspaces: dict[str, ReadOnlyWorkspace] = {}

        for alias, value in roots.items():
            if not isinstance(alias, str) or not alias.strip():
                raise WorkspaceError("Every root alias must be a non-empty string")

            if isinstance(value, str):
                root_path = value
                read_limit = global_read_limit
                search_limit = global_search_limit
                output_limit = global_output_limit
                deny_patterns = global_deny_patterns
                allow_patterns = global_allow_patterns
                allow_sensitive = global_allow_sensitive
            elif isinstance(value, dict):
                root_path = value.get("path")
                read_limit = int(value.get("max_read_bytes", global_read_limit))
                search_limit = int(
                    value.get("max_search_file_bytes", global_search_limit)
                )
                output_limit = int(
                    value.get("max_output_chars", global_output_limit)
                )
                deny_patterns = global_deny_patterns + tuple(
                    value.get("deny_patterns", ())
                )
                allow_patterns = global_allow_patterns + tuple(
                    value.get("allow_patterns", ())
                )
                allow_sensitive = bool(
                    value.get("allow_sensitive_files", global_allow_sensitive)
                )
            else:
                raise WorkspaceError(
                    f"Invalid config for root {alias!r}: expected string or object"
                )

            if not root_path:
                raise WorkspaceError(f"Root {alias!r} has no path")

            if read_limit <= 0 or search_limit <= 0 or output_limit <= 0:
                raise WorkspaceError("Read/search/output limits must be positive")

            workspaces[alias] = ReadOnlyWorkspace(
                root_path,
                max_read_bytes=read_limit,
                max_search_file_bytes=search_limit,
                max_output_chars=output_limit,
                deny_patterns=deny_patterns,
                allow_patterns=allow_patterns,
                allow_sensitive_files=allow_sensitive,
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
                f"Unknown root {selected!r}; available aliases: {', '.join(self.workspaces)}"
            )
        return selected, workspace

    def public_info(self) -> dict[str, Any]:
        """Return model-safe metadata without local absolute filesystem paths."""
        return {
            "mode": "read-only",
            "default_root": self.default_root,
            "roots": {
                alias: {
                    "available": workspace.root.exists() and workspace.root.is_dir(),
                    "sensitive_file_filter": not workspace.allow_sensitive_files,
                    "max_read_bytes": workspace.max_read_bytes,
                    "max_search_file_bytes": workspace.max_search_file_bytes,
                    "max_output_chars": workspace.max_output_chars,
                }
                for alias, workspace in self.workspaces.items()
            },
        }
