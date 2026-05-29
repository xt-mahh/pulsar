"""image_process tool — image manipulation using Pillow via run_in_executor.

CPU-bound Pillow operations are offloaded to a shared ThreadPoolExecutor
to avoid blocking the async event loop.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pulsar.execution.tools.base import ToolExecutionError
from pulsar.execution.tools.registry import tool

# ── Global thread pool for CPU-bound image operations ───────────────
CPU_COUNT = os.cpu_count() or 4
_image_executor = ThreadPoolExecutor(max_workers=CPU_COUNT * 2)

# ── Limits ────────────────────────────────────────────────────────────
MAX_INPUT_RESOLUTION = 4096  # px per side
MAX_INPUT_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
SUPPORTED_FORMATS = {"JPEG", "PNG", "GIF", "WebP", "BMP", "TIFF"}


def _run_in_executor(sync_fn):
    """Run a synchronous (CPU-bound) function in the thread pool."""
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(_image_executor, sync_fn)


@tool(
    name="image_process",
    description="Process an image: resize, crop, rotate, flip, convert format, "
                "add watermark, compress, or get info. Uses Pillow under the hood.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Processing action",
                "enum": [
                    "resize", "resize_fit", "resize_fill", "crop", "rotate",
                    "flip", "convert", "watermark", "compress", "info",
                ],
            },
            "params": {
                "type": "object",
                "description": "Action-specific parameters",
                "properties": {
                    "source_path": {
                        "type": "string",
                        "description": "Source image path (required for all actions)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output path (defaults to overwriting source)",
                    },
                    "width": {"type": "integer", "description": "Target width in px"},
                    "height": {"type": "integer", "description": "Target height in px"},
                    "x": {"type": "integer", "description": "Crop start X"},
                    "y": {"type": "integer", "description": "Crop start Y"},
                    "degrees": {"type": "number", "description": "Rotation in degrees"},
                    "format": {
                        "type": "string",
                        "description": "Target format",
                        "enum": ["JPEG", "PNG", "WebP", "GIF", "BMP"],
                    },
                    "quality": {
                        "type": "integer",
                        "description": "Compression quality (1-100)",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 85,
                    },
                    "watermark_text": {
                        "type": "string",
                        "description": "Watermark text",
                    },
                    "watermark_position": {
                        "type": "string",
                        "enum": ["center", "northwest", "northeast", "southwest", "southeast"],
                        "default": "southeast",
                    },
                },
                "required": ["source_path"],
            },
        },
        "required": ["action", "params"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "output_path": {"type": "string", "description": "Output file path"},
            "width": {"type": "integer", "description": "Output image width in px"},
            "height": {"type": "integer", "description": "Output image height in px"},
            "format": {"type": "string", "description": "Output image format"},
            "size_bytes": {"type": "integer", "description": "Output file size in bytes"},
        },
    },
)
async def image_process(action: str, params: dict) -> dict:
    """Process an image.

    CPU-bound operations (resize, crop, rotate, etc.) are run in a
    dedicated thread pool to avoid blocking the event loop.

    Supported formats: JPEG, PNG, GIF, WebP, BMP, TIFF
    Max input resolution: 4096×4096 px
    Max input file size: 50 MB
    """
    source_path = params.get("source_path", "")
    output_path = params.get("output_path", source_path)

    if not source_path:
        raise ValueError("'source_path' is required in params")

    # Validate input file
    sp = Path(source_path)
    if not sp.exists():
        raise FileNotFoundError(f"Source image not found: {source_path}")

    if sp.stat().st_size > MAX_INPUT_FILE_SIZE:
        raise ValueError(f"Image too large: {sp.stat().st_size} bytes (max {MAX_INPUT_FILE_SIZE})")

    ACTION_MAP = {
        "resize": _action_resize,
        "resize_fit": _action_resize_fit,
        "resize_fill": _action_resize_fill,
        "crop": _action_crop,
        "rotate": _action_rotate,
        "flip": _action_flip,
        "convert": _action_convert,
        "watermark": _action_watermark,
        "compress": _action_compress,
        "info": _action_info,
    }

    handler = ACTION_MAP.get(action)
    if handler is None:
        raise ValueError(f"Unknown action '{action}'. Valid: {list(ACTION_MAP.keys())}")

    try:
        return await _run_in_executor(lambda: handler(source_path, output_path, params))
    except Exception as e:
        raise ToolExecutionError(
            message=f"Image processing failed: {e}",
            tool_name="image_process",
            original=e,
        ) from e


# ══════════════════════════════════════════════════════════════════════
# Action implementations (synchronous — run in executor)
# ══════════════════════════════════════════════════════════════════════

def _open_image(source_path: str):
    """Open an image and return (PIL_Image, format)."""
    from PIL import Image
    img = Image.open(source_path)
    img.load()  # Fully load into memory
    w, h = img.size
    if w > MAX_INPUT_RESOLUTION or h > MAX_INPUT_RESOLUTION:
        raise ValueError(
            f"Image resolution {w}×{h} exceeds max {MAX_INPUT_RESOLUTION}×{MAX_INPUT_RESOLUTION}"
        )
    return img


def _save_image(img, output_path: str, quality: int = 85, fmt: str | None = None):
    """Save an image, creating parent dirs if needed."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {}
    if fmt:
        save_kwargs["format"] = fmt
    if fmt in ("JPEG", "WebP") or (fmt is None and output_path.lower().endswith((".jpg", ".jpeg"))):
        save_kwargs["quality"] = quality
    img.save(str(out), **save_kwargs)
    return {
        "output_path": str(out),
        "width": img.width,
        "height": img.height,
        "format": img.format or fmt or "unknown",
        "size_bytes": out.stat().st_size,
    }


def _action_resize(source_path: str, output_path: str, params: dict) -> dict:
    """Resize to exact dimensions (stretch if aspect ratio differs)."""
    from PIL import Image
    img = _open_image(source_path)
    w = params.get("width", img.width)
    h = params.get("height", img.height)
    img = img.resize((w, h), Image.LANCZOS)
    return _save_image(img, output_path, params.get("quality", 85))


def _action_resize_fit(source_path: str, output_path: str, params: dict) -> dict:
    """Resize to fit within a box, maintaining aspect ratio."""
    from PIL import Image
    img = _open_image(source_path)
    w = params.get("width", img.width)
    h = params.get("height", img.height)
    img.thumbnail((w, h), Image.LANCZOS)
    return _save_image(img, output_path, params.get("quality", 85))


def _action_resize_fill(source_path: str, output_path: str, params: dict) -> dict:
    """Resize to fill a box, cropping excess to maintain aspect ratio."""
    from PIL import Image
    img = _open_image(source_path)
    tw = params.get("width", img.width)
    th = params.get("height", img.height)

    # Scale so the smaller dimension fits the target
    ratio = max(tw / img.width, th / img.height)
    new_size = (int(img.width * ratio), int(img.height * ratio))
    img = img.resize(new_size, Image.LANCZOS)

    # Center crop
    left = (img.width - tw) // 2
    top = (img.height - th) // 2
    img = img.crop((left, top, left + tw, top + th))
    return _save_image(img, output_path, params.get("quality", 85))


def _action_crop(source_path: str, output_path: str, params: dict) -> dict:
    """Crop a region from the image."""
    from PIL import Image
    img = _open_image(source_path)
    x = params.get("x", 0)
    y = params.get("y", 0)
    w = params.get("width", img.width - x)
    h = params.get("height", img.height - y)
    img = img.crop((x, y, x + w, y + h))
    return _save_image(img, output_path, params.get("quality", 85))


def _action_rotate(source_path: str, output_path: str, params: dict) -> dict:
    """Rotate the image by given degrees."""
    from PIL import Image
    img = _open_image(source_path)
    degrees = params.get("degrees", 0)
    img = img.rotate(degrees, expand=True, resample=Image.BICUBIC)
    return _save_image(img, output_path, params.get("quality", 85))


def _action_flip(source_path: str, output_path: str, params: dict) -> dict:
    """Flip (mirror) the image horizontally or vertically."""
    from PIL import Image
    img = _open_image(source_path)
    direction = params.get("direction", "horizontal")
    if direction == "horizontal":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    else:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    return _save_image(img, output_path, params.get("quality", 85))


def _action_convert(source_path: str, output_path: str, params: dict) -> dict:
    """Convert image to a different format."""
    from PIL import Image
    img = _open_image(source_path)
    target_fmt = params.get("format", "JPEG")
    if target_fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{target_fmt}'. Supported: {SUPPORTED_FORMATS}")

    # Handle RGBA → RGB for JPEG
    if target_fmt == "JPEG" and img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background

    out_path = output_path
    # Auto-append extension if missing
    ext_map = {"JPEG": ".jpg", "PNG": ".png", "WebP": ".webp", "GIF": ".gif", "BMP": ".bmp"}
    if not Path(out_path).suffix:
        out_path += ext_map.get(target_fmt, ".jpg")

    return _save_image(img, out_path, params.get("quality", 85), fmt=target_fmt)


def _action_watermark(source_path: str, output_path: str, params: dict) -> dict:
    """Add a text watermark to the image."""
    from PIL import Image, ImageDraw, ImageFont
    img = _open_image(source_path)
    text = params.get("watermark_text", "")
    if not text:
        raise ValueError("'watermark_text' is required for watermark action")

    position = params.get("watermark_position", "southeast")
    draw = ImageDraw.Draw(img)

    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except (IOError, OSError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    padding = 20

    pos_map = {
        "center": ((img.width - tw) // 2, (img.height - th) // 2),
        "northwest": (padding, padding),
        "northeast": (img.width - tw - padding, padding),
        "southwest": (padding, img.height - th - padding),
        "southeast": (img.width - tw - padding, img.height - th - padding),
    }
    xy = pos_map.get(position, pos_map["southeast"])

    # Semi-transparent white text
    draw.text(xy, text, font=font, fill=(255, 255, 255, 180))
    return _save_image(img, output_path, params.get("quality", 85))


def _action_compress(source_path: str, output_path: str, params: dict) -> dict:
    """Compress image by adjusting quality."""
    from PIL import Image
    img = _open_image(source_path)
    quality = params.get("quality", 85)
    return _save_image(img, output_path, quality=quality)


def _action_info(source_path: str, output_path: str, params: dict) -> dict:
    """Get image metadata without modifying it."""
    from PIL import Image
    img = _open_image(source_path)
    return {
        "output_path": source_path,
        "width": img.width,
        "height": img.height,
        "format": img.format or "unknown",
        "size_bytes": Path(source_path).stat().st_size,
        "mode": img.mode,
        "is_animated": getattr(img, "is_animated", False),
        "n_frames": getattr(img, "n_frames", 1),
    }


async def shutdown_executor() -> None:
    """Shut down the image processing thread pool (call on system shutdown)."""
    _image_executor.shutdown(wait=True)


__all__ = ["image_process", "shutdown_executor"]
