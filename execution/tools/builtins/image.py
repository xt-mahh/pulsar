"""图片处理工具 — 基础图片操作（裁剪、缩放、格式转换）"""

import logging
from pathlib import Path
from typing import Any

from PIL import Image

from execution.tools.base import tool

logger = logging.getLogger("pulsar.tools.image")


@tool(name="image_process", description="图片基础处理：裁剪、缩放、格式转换")
async def image_process(
    path: str,
    operations: list[dict[str, Any]] | None = None,
    output_path: str | None = None,
    output_format: str | None = None,
) -> dict[str, Any]:
    """图片处理工具

    Args:
        path: 输入图片路径
        operations: 操作列表，每个操作为 {"type": "...", "params": {...}}
            支持的操作类型:
            - resize: {"width": 800, "height": 600, "keep_ratio": true}
            - crop: {"left": 0, "top": 0, "right": 100, "bottom": 100}
            - convert: {"format": "PNG"}  # JPEG, PNG, WEBP
        output_path: 输出路径（可选，默认覆盖原文件）
        output_format: 输出格式（可选，如 JPEG, PNG, WEBP）

    Returns:
        {
            "path": "...",
            "width": 800,
            "height": 600,
            "format": "JPEG",
            "size": 12345
        }
    """
    img_path = Path(path)
    if not img_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {path}")

    img = Image.open(img_path)
    original_format = img.format or "PNG"

    if operations:
        for op in operations or []:
            op_type = op.get("type", "")
            params = op.get("params", {})

            if op_type == "resize":
                width = params.get("width", img.width)
                height = params.get("height", img.height)
                keep_ratio = params.get("keep_ratio", True)

                if keep_ratio:
                    img.thumbnail((width, height), Image.LANCZOS)
                else:
                    img = img.resize((width, height), Image.LANCZOS)

                logger.debug(f"图片缩放: {img_path.name} → {width}x{height}")

            elif op_type == "crop":
                box = (
                    params.get("left", 0),
                    params.get("top", 0),
                    params.get("right", img.width),
                    params.get("bottom", img.height),
                )
                img = img.crop(box)
                logger.debug(f"图片裁剪: {img_path.name} → {box}")

            elif op_type == "convert":
                fmt = params.get("format", original_format)
                output_format = fmt

            else:
                logger.warning(f"不支持的图片操作: {op_type}")

    # 确定输出路径
    out_path = Path(output_path) if output_path else img_path
    fmt = output_format or original_format

    # 确保输出目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存
    img.save(out_path, format=fmt)
    file_size = out_path.stat().st_size

    logger.info(f"图片已处理: {path} → {out_path} ({img.width}x{img.height}, {fmt})")

    return {
        "path": str(out_path),
        "width": img.width,
        "height": img.height,
        "format": fmt,
        "size": file_size,
    }