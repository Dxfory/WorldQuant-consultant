from pathlib import Path

from PIL import Image

from pixel_intact import inspect_image, plan_slice


def test_inspect_reports_full_canvas(tmp_path: Path) -> None:
    path = tmp_path / "frame.png"
    Image.new("RGBA", (64, 48), (12, 24, 36, 255)).save(path)
    report = inspect_image(path)
    assert report.width == 64
    assert report.height == 48
    assert report.pixels == 3072
    assert report.has_alpha
    assert report.is_complete_canvas
    assert len(report.pixel_sha256) == 64


def test_size_plan_covers_uneven_edges() -> None:
    plan = plan_slice(100, 90, tile_width=40, tile_height=40)
    assert plan.complete
    assert plan.cols == 3
    assert plan.rows == 3
    assert plan.tiles[-1].width == 20
    assert plan.tiles[-1].height == 10
    assert plan.discarded_pixels == 0
