"""文件读写工具 — 异步文件操作"""

import logging
from pathlib import Path
from typing import Any

import aiofiles

from execution.tools.base import tool

logger = logging.getLogger("pulsar.tools.fileio")


@tool(name="file_read", description="读取文件内容")
async def file_read(path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """读取文件内容

    Args:
        path: 文件路径
        encoding: 文件编码，默认 utf-8

    Returns:
        {
            "path": "...",
            "content": "...",
            "size": 1234,
            "exists": True
        }
    """
    file_path = Path(path)
    if not file_path.exists():
        return {
            "path": str(file_path),
            "content": None,
            "size": 0,
            "exists": False,
        }

    async with aiofiles.open(file_path, "r", encoding=encoding) as f:
        content = await f.read()

    return {
        "path": str(file_path),
        "content": content,
        "size": len(content),
        "exists": True,
    }


@tool(name="file_write", description="写入内容到文件")
async def file_write(
    path: str,
    content: str,
    encoding: str = "utf-8",
    append: bool = False,
) -> dict[str, Any]:
    """写入内容到文件

    Args:
        path: 文件路径
        content: 要写入的内容
        encoding: 文件编码，默认 utf-8
        append: 是否追加模式，默认 False（覆盖）

    Returns:
        {
            "path": "...",
            "size": 1234,
            "success": True
        }
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    async with aiofiles.open(file_path, mode, encoding=encoding) as f:
        await f.write(content)

    logger.info(f"文件已写入: {path} ({len(content)} 字符)")
    return {
        "path": str(file_path),
        "size": len(content),
        "success": True,
    }