"""file_read and file_write tools using aiofiles for async file I/O."""

import os
from pathlib import Path

import aiofiles
import aiofiles.os as aio_os

from pulsar.execution.tools.registry import tool

# ── Protected paths that write operations must never touch ──────────
PROTECTED_PATHS = {"/etc", "/proc", "/sys", "/dev", "/boot", "/bin", "/sbin", "/usr", "/lib"}
MAX_READ_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_WRITE_SIZE = 50 * 1024 * 1024  # 50 MB


def _is_protected(path: str) -> bool:
    """Check if a path is in the protected system paths list."""
    resolved = os.path.normpath(os.path.abspath(path))
    for protected in PROTECTED_PATHS:
        if resolved.startswith(protected + os.sep) or resolved == protected:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# file_read
# ══════════════════════════════════════════════════════════════════════

@tool(
    name="file_read",
    description="Read a local file's content. Supports offset and size limits. "
                "Auto-detects encoding. Suitable for text and JSON files.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (absolute or relative to cwd)",
            },
            "offset": {
                "type": "integer",
                "description": "Read start offset in bytes (for chunked reading)",
                "default": 0,
                "minimum": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Max bytes to read. -1 means read to end.",
                "default": -1,
                "minimum": -1,
                "maximum": MAX_READ_SIZE,
            },
        },
        "required": ["path"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "File content (text)"},
            "size": {"type": "integer", "description": "Total file size in bytes"},
            "encoding": {"type": "string", "description": "Detected file encoding"},
            "mime_type": {"type": "string", "description": "File MIME type"},
        },
    },
)
async def file_read(path: str, offset: int = 0, limit: int = -1) -> dict:
    """Read a local file.

    Limitations:
        - Max read size: 10 MB
        - Encoding detection: UTF-8 → GBK → Latin-1

    Returns:
        {"content": "...", "size": N, "encoding": "utf-8", "mime_type": "text/plain"}
    """
    resolved = Path(path).resolve()
    stat = await aio_os.stat(str(resolved))
    file_size = stat.st_size

    if file_size > MAX_READ_SIZE:
        raise ValueError(f"File too large: {file_size} bytes (max {MAX_READ_SIZE})")

    # Detect encoding
    encoding = _detect_encoding(resolved)

    async with aiofiles.open(str(resolved), mode="r", encoding=encoding) as f:
        if offset > 0:
            await f.seek(offset)
        if limit > 0:
            content = await f.read(limit)
        else:
            content = await f.read()

    mime_type = _guess_mime(resolved.suffix)

    return {
        "content": content,
        "size": file_size,
        "encoding": encoding,
        "mime_type": mime_type,
    }


# ══════════════════════════════════════════════════════════════════════
# file_write
# ══════════════════════════════════════════════════════════════════════

@tool(
    name="file_write",
    description="Write content to a local file. Auto-creates parent directories. "
                "Supports text and JSON (dict → auto-serialized) content.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (absolute or relative)",
            },
            "content": {
                "type": ["string", "object"],
                "description": "Content to write. Dict is auto-serialized as JSON (indent=2).",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding",
                "default": "utf-8",
                "enum": ["utf-8", "gbk", "latin-1", "ascii"],
            },
        },
        "required": ["path", "content"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full written path"},
            "size": {"type": "integer", "description": "Bytes written"},
            "encoding": {"type": "string", "description": "Actual encoding used"},
        },
    },
)
async def file_write(path: str, content: str | dict, encoding: str = "utf-8") -> dict:
    """Write content to a local file.

    Limitations:
        - Cannot overwrite system-critical files (/etc/, /proc/, /sys/, /dev/ etc.)
        - Max write size: 50 MB
        - Auto-creates parent directories

    Returns:
        {"path": "...", "size": N, "encoding": "utf-8"}
    """
    resolved = Path(path).resolve()

    if _is_protected(str(resolved)):
        raise PermissionError(f"Cannot write to protected path: {resolved}")

    # Serialize dict content as JSON
    if isinstance(content, dict):
        import json
        content = json.dumps(content, ensure_ascii=False, indent=2)

    # Create parent directories
    resolved.parent.mkdir(parents=True, exist_ok=True)

    encoded = content.encode(encoding)
    if len(encoded) > MAX_WRITE_SIZE:
        raise ValueError(
            f"Content too large: {len(encoded)} bytes (max {MAX_WRITE_SIZE})"
        )

    async with aiofiles.open(str(resolved), mode="w", encoding=encoding) as f:
        await f.write(content)

    return {
        "path": str(resolved),
        "size": len(encoded),
        "encoding": encoding,
    }


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

ENCODING_CANDIDATES = ["utf-8", "gbk", "latin-1"]


def _detect_encoding(path: Path) -> str:
    """Detect file encoding by trial read."""
    for enc in ENCODING_CANDIDATES:
        try:
            with open(path, "r", encoding=enc) as f:
                f.read(1024)
            return enc
        except (UnicodeDecodeError, Exception):
            continue
    return "utf-8"


def _guess_mime(suffix: str) -> str:
    """Guess MIME type from file extension."""
    mime_map = {
        ".txt": "text/plain",
        ".json": "application/json",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".xml": "application/xml",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".csv": "text/csv",
        ".py": "text/x-python",
        ".js": "application/javascript",
        ".css": "text/css",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    return mime_map.get(suffix.lower(), "application/octet-stream")


__all__ = ["file_read", "file_write"]
