from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from .completeness import load_intact_image

MAX_EDGE = 16_384
MAX_PIXELS = 80_000_000


@dataclass(frozen=True)
class EnhanceSettings:
    scale: float = 2.0
    sharpness: float = 0.85
    clarity: float = 0.35
    contrast: float = 1.0
    denoise: bool = False
    autocontrast: bool = False

    def __post_init__(self) -> None:
        if self.scale < 1:
            raise ValueError("scale must be at least 1")
        if not 0 <= self.clarity <= 1.5:
            raise ValueError("clarity must be between 0 and 1.5")
        if not 0 <= self.sharpness <= 2:
            raise ValueError("sharpness must be between 0 and 2")


def target_size(width: int, height: int, scale: float) -> tuple[int, int]:
    return max(1, round(width * scale)), max(1, round(height * scale))


def assert_safe_size(width: int, height: int) -> None:
    if width > MAX_EDGE or height > MAX_EDGE or width * height > MAX_PIXELS:
        raise ValueError(
            f"output {width}×{height} exceeds the safe limit "
            f"({MAX_EDGE}px edge or {MAX_PIXELS} pixels). Use a smaller scale."
        )


def enhance_pil(image: Image.Image, settings: EnhanceSettings | None = None) -> Image.Image:
    """Upscale with Lanczos, then add mid-frequency clarity and edge sharpen.

    Color is left alone unless contrast/autocontrast is requested. This is not
    generative fill: composition stays complete.
    """
    settings = settings or EnhanceSettings()
    has_alpha = "A" in image.getbands()
    alpha = image.getchannel("A") if has_alpha else None
    working = image.convert("RGB") if image.mode != "RGB" else image.copy()

    if settings.denoise:
        working = working.filter(ImageFilter.MedianFilter(size=3))

    if settings.scale != 1:
        width, height = target_size(working.width, working.height, settings.scale)
        assert_safe_size(width, height)
        working = working.resize((width, height), resample=Image.Resampling.LANCZOS)
        if alpha is not None:
            alpha = alpha.resize((width, height), resample=Image.Resampling.LANCZOS)

    if settings.autocontrast:
        from PIL import ImageOps

        working = ImageOps.autocontrast(working, cutoff=0.2)

    # Clarity is a wide-radius unsharp (Lightroom-style local contrast).
    if settings.clarity > 0:
        working = working.filter(
            ImageFilter.UnsharpMask(
                radius=14,
                percent=int(round(settings.clarity * 160)),
                threshold=6,
            )
        )
    # Sharpen is a tight-radius unsharp. Do not stack ImageEnhance.Sharpness on top.
    if settings.sharpness > 0:
        working = working.filter(
            ImageFilter.UnsharpMask(
                radius=1.4,
                percent=int(round(settings.sharpness * 120)),
                threshold=2,
            )
        )
    if settings.contrast != 1:
        working = ImageEnhance.Contrast(working).enhance(settings.contrast)

    if alpha is not None:
        working = working.convert("RGBA")
        working.putalpha(alpha)
    return working


def enhance_image(
    path: str | Path,
    out_path: str | Path,
    settings: EnhanceSettings | None = None,
) -> Image.Image:
    working = enhance_pil(load_intact_image(path), settings)
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
