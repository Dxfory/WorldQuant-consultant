from pathlib import Path

from PIL import Image

from pixel_intact.cli import main


def test_cli_inspect_slice_join(tmp_path: Path, capsys) -> None:
    source = tmp_path / "cli.png"
    Image.new("RGB", (30, 20), (9, 18, 27)).save(source)
    tiles = tmp_path / "tiles"
    restored = tmp_path / "restored.png"

    assert main(["inspect", str(source)]) == 0
    assert "600" in capsys.readouterr().out

    assert main(["slice", str(source), "--cols", "2", "--rows", "2", "--out", str(tiles)]) == 0
    out = capsys.readouterr().out
    assert '"complete": true' in out
    assert '"discarded_pixels": 0' in out

    assert main(["join", str(tiles), "--out", str(restored), "--original", str(source)]) == 0
    assert '"matches_original": true' in capsys.readouterr().out
    assert restored.exists()
