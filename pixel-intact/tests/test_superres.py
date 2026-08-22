from pathlib import Path

import pytest
from PIL import Image

from pixel_intact import EnhanceSettings, enhance_image, fsr_available


def test_fsr_engine_doubles_pixels(tmp_path: Path) -> None:
    if not fsr_available():
        pytest.skip("FSRCNN models or OpenCV not available")
    source = tmp_path / "tiny.png"
    Image.new("RGB", (20, 12), (30, 60, 90)).save(source)
    output = tmp_path / "fsr.png"
    result = enhance_image(
        source,
        output,
        EnhanceSettings(scale=2, clarity=0, sharpness=0, engine="fsr"),
    )
    assert result.size == (40, 24)


def test_fsr_below_two_falls_back_to_lanczos(tmp_path: Path) -> None:
    source = tmp_path / "tiny.png"
    Image.new("RGB", (20, 12), (30, 60, 90)).save(source)
    result = enhance_image(
        source,
        tmp_path / "one-five.png",
        EnhanceSettings(scale=1.5, clarity=0, sharpness=0, engine="fsr"),
    )
    assert result.size == (30, 18)
