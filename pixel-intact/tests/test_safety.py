from io import BytesIO

from PIL import Image

from pixel_intact.safety import MAX_IMAGE_PIXELS, allow_large_local_images, open_local_image


def test_pillow_limit_covers_poster_original() -> None:
    allow_large_local_images()
    assert Image.MAX_IMAGE_PIXELS >= 130_142_460
    assert MAX_IMAGE_PIXELS >= 400_000_000


def test_open_local_png_roundtrip() -> None:
    buffer = BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(buffer, format="PNG")
    buffer.seek(0)
    image = open_local_image(buffer)
    assert image.size == (32, 24)
