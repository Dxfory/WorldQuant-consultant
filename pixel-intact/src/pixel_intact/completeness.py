from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .safety import open_local_image


@dataclass(frozen=True)
class ImageReport:
    path: str
    format: str | None
    mode: str
    width: int
    height: int
    pixels: int
    has_alpha: bool
    dpi: tuple[float, float] | None
    pixel_sha256: str
    info: dict[str, Any]

    @property
    def is_complete_canvas(self) -> bool:
        """True when the loaded bitmap matches the file's stated pixel size."""
        return self.width > 0 and self.height > 0 and self.pixels == self.width * self.height


def _sha256_pixels(image: Image.Image) -> str:
    payload = image.tobytes()
    return hashlib.sha256(payload).hexdigest()


def load_intact_image(path: str | Path) -> Image.Image:
    """Open an image and apply EXIF orientation without resampling."""
    return open_local_image(path)


def inspect_image(path: str | Path) -> ImageReport:
    image = load_intact_image(path)
    dpi = image.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) == 2:
        dpi_value = (float(dpi[0]), float(dpi[1]))
    else:
        dpi_value = None
    return ImageReport(
        path=str(path),
        format=image.format,
        mode=image.mode,
        width=image.width,
        height=image.height,
        pixels=image.width * image.height,
        has_alpha="A" in image.getbands(),
        dpi=dpi_value,
        pixel_sha256=_sha256_pixels(image.convert("RGBA")),
        info={key: value for key, value in image.info.items() if isinstance(key, str)},
    )
