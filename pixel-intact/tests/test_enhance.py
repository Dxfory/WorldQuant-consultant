from pathlib import Path

from PIL import Image

from pixel_intact import EnhanceSettings, enhance_image, inspect_image


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
