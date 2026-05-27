from io import BytesIO
from pathlib import Path
from PIL import Image
from execution.tools.registry import tool


@tool(name="image_process", description="图片处理：裁剪、缩放、格式转换")
async def image_process(
    path: str,
    resize: tuple = None,
    crop: tuple = None,
    format: str = None,
    quality: int = 85,
    output_path: str = None,
) -> dict:
    img = Image.open(path)
    original_size = img.size

    if crop:
        img = img.crop(crop)
    if resize:
        img = img.resize(resize, Image.LANCZOS)

    output = output_path or path
    if format:
        img = img.convert("RGB") if format.upper() in ("JPEG", "JPG") else img
        img.save(output, format=format.upper(), quality=quality)
    else:
        img.save(output, quality=quality)

    return {
        "original_size": original_size,
        "new_size": img.size,
        "output_path": str(Path(output).absolute()),
    }