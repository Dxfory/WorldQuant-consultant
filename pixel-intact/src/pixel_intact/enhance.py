from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from .completeness import load_intact_image
from .export import save_image
from .superres import fsr_available, pick_fsr_factor, upscale_fsr

MAX_EDGE = 16_384
MAX_PIXELS = 120_000_000


@dataclass(frozen=True)
class EnhanceSettings:
    scale: float = 2.0
    sharpness: float = 0.85
    clarity: float = 0.35
    contrast: float = 1.0
    denoise: bool = False
    autocontrast: bool = False
    engine: str = "lanczos"

    def __post_init__(self) -> None:
        if self.scale < 1:
            raise ValueError("scale must be at least 1")
        if not 0 <= self.clarity <= 1.5:
            raise ValueError("clarity must be between 0 and 1.5")
        if not 0 <= self.sharpness <= 2:
            raise ValueError("sharpness must be between 0 and 2")
        if self.engine not in {"lanczos", "fsr"}:
            raise ValueError("engine must be lanczos or fsr")


def target_size(width: int, height: int, scale: float) -> tuple[int, int]:
    return max(1, round(width * scale)), max(1, round(height * scale))


def output_exceeds(width: int, height: int, scale: float = 1.0) -> bool:
    out_width, out_height = target_size(width, height, scale)
    return out_width > MAX_EDGE or out_height > MAX_EDGE or out_width * out_height > MAX_PIXELS


def assert_safe_size(width: int, height: int) -> None:
    if output_exceeds(width, height, 1):
        raise ValueError(
            f"整张输出 {width}×{height} 超过安全上限（边长 {MAX_EDGE}px 或 {MAX_PIXELS} 像素）。"
            f"请把放大改小，或先切图再对每一块提高清晰度。"
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
        if settings.engine == "fsr" and pick_fsr_factor(settings.scale):
            if not fsr_available():
                raise ValueError("FSRCNN 超分不可用：请安装 opencv-contrib-python-headless 并放入 models/FSRCNN_x2.pb")
            working = upscale_fsr(working, settings.scale)
        else:
            working = working.resize((width, height), resample=Image.Resampling.LANCZOS)
        if alpha is not None:
            alpha = alpha.resize((working.width, working.height), resample=Image.Resampling.LANCZOS)

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
    save_image(working, destination, fmt=destination.suffix.lower().lstrip(".") or "png")
    return working
