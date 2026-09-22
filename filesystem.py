from __future__ import annotations

import codecs
import fnmatch
import os
from pathlib import Path
from typing import Any, Iterator


DEFAULT_MAX_READ_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_SEARCH_FILE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_OUTPUT_CHARS = 256 * 1024

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

DEFAULT_DENY_PATTERNS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "**/*.pem",
    "*.key",
    "**/*.key",
    "id_rsa",
    "**/id_rsa",
    "id_ed25519",
    "**/id_ed25519",
    "credentials.json",
    "**/credentials.json",
    "service-account*.json",
    "**/service-account*.json",
    ".npmrc",
    "**/.npmrc",
    ".pypirc",
    "**/.pypirc",
    ".netrc",
    "**/.netrc",
    ".ssh",
    "**/.ssh",
    ".ssh/**",
    "**/.ssh/**",
    ".aws",
    "**/.aws",
    ".aws/**",
    "**/.aws/**",
)

DEFAULT_ALLOW_PATTERNS = (
    ".env.example",
    "**/.env.example",
    ".env.sample",
    "**/.env.sample",
    ".env.template",
    "**/.env.template",
)


class WorkspaceError(ValueError):
    """Raised when a requested filesystem operation is invalid or unsafe."""


class ReadOnlyWorkspace:
    def __init__(
        self,
        root: str | Path,
        *,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_search_file_bytes: int = DEFAULT_MAX_SEARCH_FILE_BYTES,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        deny_patterns: tuple[str, ...] | list[str] = (),
        allow_patterns: tuple[str, ...] | list[str] = DEFAULT_ALLOW_PATTERNS,
        allow_sensitive_files: bool = False,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)
        self.max_read_bytes = int(max_read_bytes)
        self.max_search_file_bytes = int(max_search_file_bytes)
        self.max_output_chars = int(max_output_chars)
        self.allow_sensitive_files = bool(allow_sensitive_files)

        configured_denies = tuple(str(p) for p in deny_patterns)
        self.deny_patterns = (
            configured_denies
            if self.allow_sensitive_files
            else DEFAULT_DENY_PATTERNS + configured_denies
        )
        self.allow_patterns = tuple(str(p) for p in allow_patterns)

    def _check_root(self) -> None:
        if not self.root.exists():
            raise WorkspaceError("Configured root does not exist")
        if not self.root.is_dir():
            raise WorkspaceError("Configured root is not a directory")

    def _relative_unchecked(self, path: Path) -> str:
        return "." if path == self.root else path.relative_to(self.root).as_posix()

    @staticmethod
    def _matches(path: str, pattern: str) -> bool:
        return fnmatch.fnmatch(path.casefold(), pattern.casefold())

    def is_denied(self, relative_path: str) -> bool:
        relative_path = relative_path.replace("\\", "/")
        while relative_path.startswith("./"):
            relative_path = relative_path[2:]
        if not relative_path:
            return False

        if any(self._matches(relative_path, p) for p in self.allow_patterns):
            return False

        return any(self._matches(relative_path, p) for p in self.deny_patterns)

    def resolve(self, user_path: str = "") -> Path:
        """Resolve a path and guarantee it remains inside the configured root."""
        self._check_root()
        raw = (user_path or "").strip()
        candidate = Path(raw) if raw else self.root

        if not candidate.is_absolute():
            candidate = self.root / candidate

        try:
            resolved = candidate.expanduser().resolve(strict=True)
        except FileNotFoundError as exc:
            raise WorkspaceError("Path does not exist") from exc

        try:
            relative = self._relative_unchecked(resolved)
        except ValueError as exc:
            raise WorkspaceError("Access denied: path escapes configured root") from exc

        if self.is_denied(relative):
            raise WorkspaceError("Access denied by sensitive-file policy")

        return resolved

    def relative(self, path: Path) -> str:
        return self._relative_unchecked(path)

    @staticmethod
    def _is_junction(path: Path) -> bool:
        checker = getattr(path, "is_junction", None)
        return bool(checker()) if checker else False

    def _safe_child(self, path: Path) -> Path | None:
        try:
            resolved = path.resolve(strict=True)
            relative = self._relative_unchecked(resolved)
        except (OSError, ValueError):
            return None

        if self.is_denied(relative):
            return None

        return resolved

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
            if child.is_symlink() or self._is_junction(child):
                resolved = self._safe_child(child)
                if resolved is None:
                    continue
                continue

            if self._safe_child(child) is None:
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
                resolved = self._safe_child(current / name)
                if resolved is not None and resolved.is_file():
                    yield resolved

    @staticmethod
    def _looks_binary_without_bom(prefix: bytes) -> bool:
        if b"\x00" in prefix:
            return True
        if not prefix:
            return False
        control = sum(1 for byte in prefix if byte < 9 or 13 < byte < 32)
        return control / len(prefix) > 0.10

    @classmethod
    def detect_encoding(cls, prefix: bytes, requested: str = "auto") -> str:
        if requested != "auto":
            try:
                codecs.lookup(requested)
            except LookupError as exc:
                raise WorkspaceError(f"Unknown encoding: {requested}") from exc
            return requested

        if prefix.startswith(codecs.BOM_UTF8):
            return "utf-8-sig"
        if prefix.startswith(codecs.BOM_UTF16_LE) or prefix.startswith(codecs.BOM_UTF16_BE):
            return "utf-16"
        if prefix.startswith(codecs.BOM_UTF32_LE) or prefix.startswith(codecs.BOM_UTF32_BE):
            return "utf-32"

        if cls._looks_binary_without_bom(prefix):
            raise WorkspaceError("Binary file detected")

        for encoding in ("utf-8", "gb18030"):
            try:
                prefix.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue

        raise WorkspaceError("Unsupported text encoding or binary file")

    def _open_text(self, target: Path, encoding: str = "auto"):
        with target.open("rb") as stream:
            prefix = stream.read(8192)
        selected = self.detect_encoding(prefix, encoding)
        try:
            return target.open("r", encoding=selected, errors="strict"), selected
        except (LookupError, UnicodeError) as exc:
            raise WorkspaceError("Unable to open text file with selected encoding") from exc

    def stat(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        stat = target.stat()
        return {
            "path": self.relative(target),
            "type": "directory" if target.is_dir() else "file",
            "size_bytes": stat.st_size,
            "modified_time_unix": stat.st_mtime,
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
            raise WorkspaceError("Not a directory")

        max_depth = max(0, min(int(max_depth), 10))
        max_entries = max(1, min(int(max_entries), 2000))
        entries: list[dict[str, Any]] = []
        truncated = False

        def append_entry(path_obj: Path) -> bool:
            nonlocal truncated
            if len(entries) >= max_entries:
                truncated = True
                return False

            resolved = self._safe_child(path_obj)
            if resolved is None:
                return True

            try:
                stat = resolved.stat()
            except OSError:
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
            try:
                children = sorted(
                    target.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.casefold()),
                )
            except OSError as exc:
                raise WorkspaceError("Unable to list directory") from exc

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

                visible_dirs = list(dirs)
                if depth >= max_depth:
                    dirs[:] = []
                    visible_dirs = []

                for name in sorted([*visible_dirs, *files], key=str.casefold):
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
        """Read a bounded line range without loading the whole file into memory."""
        target = self.resolve(path)
        if not target.is_file():
            raise WorkspaceError("Not a file")

        start = max(1, int(start_line))
        requested_end = max(start, int(end_line))
        end = min(requested_end, start + 1999)

        try:
            stream, used_encoding = self._open_text(target, encoding)
        except OSError as exc:
            raise WorkspaceError("Unable to open file") from exc

        output: list[str] = []
        output_chars = 0
        output_bytes = 0
        last_line = start - 1
        more_lines_exist = False

        try:
            with stream:
                for line_number, raw_line in enumerate(stream, start=1):
                    if line_number < start:
                        continue
                    if line_number > end:
                        more_lines_exist = True
                        break

                    line = raw_line.rstrip("\r\n")
                    rendered = f"{line_number} | {line}"
                    rendered_chars = len(rendered) + 1
                    rendered_bytes = len(rendered.encode(used_encoding, errors="strict"))
                    if (
                        output_chars + rendered_chars > self.max_output_chars
                        or output_bytes + rendered_bytes > self.max_read_bytes
                    ):
                        more_lines_exist = True
                        break

                    output.append(rendered)
                    output_chars += rendered_chars
                    output_bytes += rendered_bytes
                    last_line = line_number
        except UnicodeDecodeError as exc:
            raise WorkspaceError(
                f"Unable to decode file using encoding={used_encoding!r}"
            ) from exc

        return {
            "path": self.relative(target),
            "encoding": used_encoding,
            "size_bytes": target.stat().st_size,
            "start_line": start,
            "end_line": last_line,
            "truncated": more_lines_exist or requested_end > end,
            "content": "\n".join(output),
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
            raise WorkspaceError("Not a directory")

        limit = max(1, min(int(max_results), 1000))
        needle = pattern.casefold()
        results: list[dict[str, Any]] = []

        for file_path in self.iter_files(base, include_hidden=include_hidden):
            relative = self.relative(file_path)
            if fnmatch.fnmatch(file_path.name.casefold(), needle) or fnmatch.fnmatch(
                relative.casefold(), needle
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
        needle = query if case_sensitive else query.casefold()
        results: list[dict[str, Any]] = []
        skipped_binary = 0
        skipped_large = 0
        skipped_decode = 0

        for file_path in self.iter_files(base, include_hidden=include_hidden):
            if not fnmatch.fnmatch(file_path.name.casefold(), file_glob.casefold()):
                continue

            try:
                size = file_path.stat().st_size
                if size > self.max_search_file_bytes:
                    skipped_large += 1
                    continue

                try:
                    stream, used_encoding = self._open_text(file_path)
                except WorkspaceError:
                    skipped_binary += 1
                    continue

                try:
                    with stream:
                        for line_number, raw_line in enumerate(stream, start=1):
                            line = raw_line.rstrip("\r\n")
                            haystack = line if case_sensitive else line.casefold()
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
                                        "skipped_decode": skipped_decode,
                                        "results": results,
                                    }
                except UnicodeDecodeError:
                    skipped_decode += 1
                    continue

            except (OSError, PermissionError):
                continue

        return {
            "query": query,
            "file_glob": file_glob,
            "count": len(results),
            "truncated": False,
            "skipped_binary": skipped_binary,
            "skipped_large": skipped_large,
            "skipped_decode": skipped_decode,
            "results": results,
        }
