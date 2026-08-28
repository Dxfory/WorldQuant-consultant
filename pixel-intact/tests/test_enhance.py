from pathlib import Path

import pytest
from PIL import Image

from pixel_intact import EnhanceSettings, enhance_image, inspect_image
from pixel_intact.enhance import MAX_EDGE, assert_safe_size


def test_enhance_increases_pixel_count(tmp_path: Path) -> None:
    source = tmp_path / "small.png"
    Image.new("RGB", (32, 24), (40, 80, 120)).save(source)
    output = tmp_path / "large.png"

    enhance_image(source, output, EnhanceSettings(scale=4, clarity=0.3, sharpness=1.2))

    report = inspect_image(output)
    assert report.width == 128
    assert report.height == 96
    assert report.pixels == 128 * 96
    assert report.pixels > inspect_image(source).pixels


def test_enhance_preserves_alpha_and_scale_one(tmp_path: Path) -> None:
    source = tmp_path / "alpha.png"
    image = Image.new("RGBA", (16, 16), (10, 20, 30, 200))
    image.save(source)
    output = tmp_path / "same.png"

    result = enhance_image(source, output, EnhanceSettings(scale=1, clarity=0.1, sharpness=1.0))

    assert result.mode == "RGBA"
    assert result.size == (16, 16)
    assert result.getchannel("A").getextrema()[0] > 0


def test_enhance_keeps_flat_color(tmp_path: Path) -> None:
    source = tmp_path / "flat.png"
    color = (80, 90, 100)
    Image.new("RGB", (24, 24), color).save(source)
    result = enhance_image(
        source,
        tmp_path / "flat-2x.png",
        EnhanceSettings(scale=2, clarity=0.3, sharpness=0.8),
    )
    sample = result.getpixel((12, 12))
    assert all(abs(left - right) <= 3 for left, right in zip(sample, color))


def test_reject_unsafe_output_size() -> None:
    with pytest.raises(ValueError, match="超过安全上限"):
        assert_safe_size(MAX_EDGE + 1, 10)


def test_three_by_two_tile_at_2x_is_allowed() -> None:
    assert_safe_size(6336, 13692)
    with pytest.raises(ValueError, match="超过安全上限"):
        assert_safe_size(19010, 27384)
