from pathlib import Path

from PIL import Image

from pixel_intact import EnhanceSettings, batch_enhance
from pixel_intact.cli import main


def test_batch_enhances_folder(tmp_path: Path) -> None:
    folder = tmp_path / "in"
    folder.mkdir()
    Image.new("RGB", (10, 8), (1, 2, 3)).save(folder / "a.png")
    Image.new("RGB", (12, 9), (4, 5, 6)).save(folder / "b.png")
    out = tmp_path / "out"
    written = batch_enhance(folder, out, EnhanceSettings(scale=2, clarity=0, sharpness=0))
    assert len(written) == 2
    assert Image.open(out / "a-enhanced.png").size == (20, 16)


def test_cli_batch(tmp_path: Path) -> None:
    folder = tmp_path / "in"
    folder.mkdir()
    Image.new("RGB", (8, 8), (9, 9, 9)).save(folder / "c.png")
    out = tmp_path / "out"
    assert main(["batch", str(folder), "--out", str(out), "--scale", "2", "--clarity", "0", "--sharpness", "0"]) == 0
    assert (out / "c-enhanced.png").exists()
