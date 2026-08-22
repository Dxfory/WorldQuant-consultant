from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .completeness import load_intact_image


@dataclass(frozen=True)
class EnhanceSettings:
    scale: float = 2.0
    sharpness: float = 1.35
    clarity: float = 0.28
    contrast: float = 1.06
    denoise: bool = False

    def __post_init__(self) -> None:
        if self.scale < 1:
            raise ValueError("scale must be at least 1")
        if not 0 <= self.clarity <= 1.5:
            raise ValueError("clarity must be between 0 and 1.5")


def _local_contrast(image: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return image
    radius = 6.0
    blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
    # High-pass midtones: original + amount * (original - blur)
    return Image.blend(blurred, image, min(1.0, 0.5 + amount / 2))


def enhance_image(
    path: str | Path,
    out_path: str | Path,
    settings: EnhanceSettings | None = None,
) -> Image.Image:
    """Upscale with Lanczos, then refine edges and local contrast.

    This is not generative fill. It keeps the original composition complete
    and only increases sample density plus perceived clarity.
    """
    settings = settings or EnhanceSettings()
    image = load_intact_image(path)
    has_alpha = "A" in image.getbands()
    alpha = image.getchannel("A") if has_alpha else None
    working = image.convert("RGB")

    if settings.denoise:
        working = working.filter(ImageFilter.MedianFilter(size=3))

    if settings.scale != 1:
        target = (
            max(1, round(working.width * settings.scale)),
            max(1, round(working.height * settings.scale)),
        )
        working = working.resize(target, resample=Image.Resampling.LANCZOS)
        if alpha is not None:
            alpha = alpha.resize(target, resample=Image.Resampling.LANCZOS)

    working = ImageOps.autocontrast(working, cutoff=0.2)
    working = _local_contrast(working, settings.clarity)
    working = working.filter(
        ImageFilter.UnsharpMask(radius=1.6, percent=int(120 * settings.sharpness), threshold=2)
    )
    working = ImageEnhance.Contrast(working).enhance(settings.contrast)
    working = ImageEnhance.Sharpness(working).enhance(settings.sharpness)
    if alpha is not None:
        working = working.convert("RGBA")
        working.putalpha(alpha)

    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        rgb = working.convert("RGB")
        rgb.save(destination, format="JPEG", quality=98, subsampling=0, optimize=True)
        return rgb
    if suffix == ".webp":
        working.save(destination, format="WEBP", lossless=True, quality=100)
        return working
    working.save(destination, format="PNG", compress_level=1)
    return working
