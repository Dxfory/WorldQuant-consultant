from __future__ import annotations

from pathlib import Path

from .enhance import EnhanceSettings, enhance_image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


def batch_enhance(
    input_dir: str | Path,
    output_dir: str | Path,
    settings: EnhanceSettings | None = None,
    fmt: str = "png",
) -> list[Path]:
    source = Path(input_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path in sorted(source.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        out_path = destination / f"{path.stem}-enhanced.{fmt.lstrip('.')}"
        enhance_image(path, out_path, settings)
        written.append(out_path)
    if not written:
        raise ValueError(f"no images found in {source}")
    return written
