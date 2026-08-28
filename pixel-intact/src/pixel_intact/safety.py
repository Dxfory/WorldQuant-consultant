"""Allow trusted local originals that exceed Pillow's public-web pixel cap."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# Pillow defaults to ~89 million pixels and treats bigger files as a zip bomb.
# A 9505×13692 illustration is 130 million pixels and is a normal original here.
MAX_IMAGE_PIXELS = 400_000_000


def allow_large_local_images() -> None:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def open_local_image(source: str | Path | BytesIO) -> Image.Image:
    allow_large_local_images()
    try:
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw)
            return image.copy()
    except Image.DecompressionBombError as error:
        raise ValueError(
            "这张图像素太多，阅读器默认会拦截。请确认已更新 Pixel Intact，"
            "然后先切块再提高每一块的清晰度。"
        ) from error
    except UnidentifiedImageError as error:
        raise ValueError("无法识别这张图，请改用 PNG / JPEG / WebP 原图。") from error


allow_large_local_images()
