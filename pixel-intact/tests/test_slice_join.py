from pathlib import Path

from PIL import Image

from pixel_intact import inspect_image, join_tiles, plan_slice, slice_image


def _make_image(path: Path, width: int = 101, height: int = 77) -> Path:
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, (x + y) % 256)
    image.save(path, format="PNG")
    return path


def test_grid_slice_keeps_every_pixel(tmp_path: Path) -> None:
    source = _make_image(tmp_path / "source.png", 101, 77)
    plan = slice_image(source, tmp_path / "tiles", cols=3, rows=2)

    assert plan.complete
    assert plan.discarded_pixels == 0
    assert plan.exported_pixels == 101 * 77
    assert plan.remainder_distributed
    assert plan.cols == 3
    assert plan.rows == 2
    assert [tile.width for tile in plan.tiles if tile.row == 0] == [34, 34, 33]
    assert [tile.height for tile in plan.tiles if tile.col == 0] == [39, 38]

    restored = tmp_path / "restored.png"
    result = join_tiles(tmp_path / "tiles", restored, original_path=source)
    assert result.complete
    assert result.matches_original is True
    assert inspect_image(restored).pixels == inspect_image(source).pixels


def test_size_slice_emits_remainder_tiles(tmp_path: Path) -> None:
    source = _make_image(tmp_path / "source.png", 50, 41)
    plan = slice_image(source, tmp_path / "tiles", tile_width=20, tile_height=20)

    assert plan.complete
    assert plan.cols == 3
    assert plan.rows == 3
    assert plan.tiles[-1].width == 10
    assert plan.tiles[-1].height == 1

    result = join_tiles(tmp_path / "tiles", tmp_path / "restored.png", original_path=source)
    assert result.matches_original is True


def test_plan_rejects_ambiguous_mode() -> None:
    try:
        plan_slice(64, 64, cols=2)
    except ValueError as error:
        assert "together" in str(error)
    else:
        raise AssertionError("expected ValueError")
