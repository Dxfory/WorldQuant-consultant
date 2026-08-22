from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image


def save_image(
    image: Image.Image,
    destination: str | Path | BytesIO,
    *,
    fmt: str = "png",
    jpeg_quality: int = 98,
) -> None:
    kind = fmt.lower().lstrip(".")
    if kind in {"jpg", "jpeg"}:
        rgb = image.convert("RGB")
        rgb.save(destination, format="JPEG", quality=jpeg_quality, subsampling=0, optimize=True)
        return
    if kind == "webp":
        image.save(destination, format="WEBP", lossless=True, quality=100)
        return
    image.save(destination, format="PNG", compress_level=1)


def encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    save_image(image, buffer, fmt="png")
    return buffer.getvalue()
