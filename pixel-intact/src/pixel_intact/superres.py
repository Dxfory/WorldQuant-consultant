from __future__ import annotations

from pathlib import Path

from PIL import Image

MODEL_NAMES = {
    2: "FSRCNN_x2.pb",
    3: "FSRCNN_x3.pb",
    4: "FSRCNN_x4.pb",
}


def _model_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        here.parents[2] / "models",
        Path.cwd() / "pixel-intact" / "models",
        Path.cwd() / "models",
    ]


def model_path(factor: int) -> Path | None:
    name = MODEL_NAMES.get(factor)
    if name is None:
        return None
    for folder in _model_dirs():
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


def fsr_available() -> bool:
    try:
        from cv2 import dnn_superres  # noqa: F401
    except Exception:
        return False
    return model_path(2) is not None


def pick_fsr_factor(scale: float) -> int | None:
    if scale >= 4:
        return 4
    if scale >= 3:
        return 3
    if scale >= 2:
        return 2
    return None


def upscale_fsr(image: Image.Image, scale: float) -> Image.Image:
    """Neural upscale with FSRCNN, then Lanczos to the exact target size."""
    import cv2
    import numpy as np
    from cv2 import dnn_superres

    factor = pick_fsr_factor(scale)
    if factor is None:
        raise ValueError("FSRCNN needs scale >= 2")
    path = model_path(factor)
    if path is None:
        raise ValueError(f"missing FSRCNN_x{factor}.pb in models/")

    target = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    working = image.convert("RGB")
    sr = dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(path))
    sr.setModel("fsrcnn", factor)
    bgr = cv2.cvtColor(np.array(working), cv2.COLOR_RGB2BGR)
    out = sr.upsample(bgr)
    rgb = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    if rgb.size != target:
        rgb = rgb.resize(target, resample=Image.Resampling.LANCZOS)
    return rgb
