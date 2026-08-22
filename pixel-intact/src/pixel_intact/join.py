from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .completeness import load_intact_image
from .slice import SliceTile


_TILE_NAME = re.compile(r"r(\d+)_c(\d+)\.(png|jpg|jpeg|webp)$", re.IGNORECASE)


@dataclass(frozen=True)
class JoinResult:
    width: int
    height: int
    tiles: int
    discarded_pixels: int
    pixel_sha256: str
    matches_original: bool | None
    output_path: str

    @property
    def complete(self) -> bool:
        return self.discarded_pixels == 0


def _parse_manifest(path: Path) -> tuple[int, int, list[SliceTile]] | None:
    if not path.exists():
        return None
    width = height = None
    tiles: list[SliceTile] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("width="):
            width = int(line.split("=", 1)[1])
        elif line.startswith("height="):
            height = int(line.split("=", 1)[1])
        elif ":" in line and line[0] == "r":
            _name, payload = line.split(":", 1)
            row, col, left, top, tile_w, tile_h = (int(part) for part in payload.split(","))
            tiles.append(
                SliceTile(row=row, col=col, left=left, top=top, width=tile_w, height=tile_h)
            )
    if width is None or height is None or not tiles:
        return None
    return width, height, tiles


def _discover_tiles(folder: Path) -> list[tuple[SliceTile, Path]]:
    found: list[tuple[SliceTile, Path]] = []
    for file_path in sorted(folder.iterdir()):
        match = _TILE_NAME.match(file_path.name)
        if not match:
            continue
        with Image.open(file_path) as image:
            found.append(
                (
                    SliceTile(
                        row=int(match.group(1)),
                        col=int(match.group(2)),
                        left=0,
                        top=0,
                        width=image.width,
                        height=image.height,
                    ),
                    file_path,
                )
            )
    if not found:
        raise ValueError(f"no rXX_cXX tiles found in {folder}")
    return found


def join_tiles(
    tiles_dir: str | Path,
    out_path: str | Path,
    *,
    original_path: str | Path | None = None,
) -> JoinResult:
    folder = Path(tiles_dir)
    parsed = _parse_manifest(folder / "intact-manifest.txt")
    if parsed is not None:
        width, height, tiles = parsed
        canvas = Image.new("RGBA", (width, height))
        used_pixels = 0
        for tile in tiles:
            piece = load_intact_image(folder / tile.name).convert("RGBA")
            if piece.size != (tile.width, tile.height):
                raise ValueError(f"{tile.name} size {piece.size} does not match manifest")
            canvas.paste(piece, (tile.left, tile.top))
            used_pixels += tile.width * tile.height
    else:
        discovered = _discover_tiles(folder)
        rows = max(tile.row for tile, _ in discovered) + 1
        cols = max(tile.col for tile, _ in discovered) + 1
        grid: dict[tuple[int, int], tuple[SliceTile, Path]] = {
            (tile.row, tile.col): (tile, path) for tile, path in discovered
        }
        row_heights = []
        for row in range(rows):
            heights = [grid[(row, col)][0].height for col in range(cols) if (row, col) in grid]
            if not heights:
                raise ValueError(f"missing entire row {row}")
            row_heights.append(max(heights))
        col_widths = []
        for col in range(cols):
            widths = [grid[(row, col)][0].width for row in range(rows) if (row, col) in grid]
            if not widths:
                raise ValueError(f"missing entire column {col}")
            col_widths.append(max(widths))
        width = sum(col_widths)
        height = sum(row_heights)
        canvas = Image.new("RGBA", (width, height))
        used_pixels = 0
        top = 0
        for row in range(rows):
            left = 0
            for col in range(cols):
                if (row, col) not in grid:
                    raise ValueError(f"missing tile r{row:02d}_c{col:02d}")
                tile, path = grid[(row, col)]
                piece = load_intact_image(path).convert("RGBA")
                canvas.paste(piece, (left, top))
                used_pixels += piece.width * piece.height
                left += col_widths[col]
            top += row_heights[row]

    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", compress_level=1)

    matches: bool | None = None
    if original_path is not None:
        original = load_intact_image(original_path).convert("RGBA")
        matches = original.size == canvas.size and original.tobytes() == canvas.tobytes()

    digest = hashlib.sha256(canvas.tobytes()).hexdigest()
    return JoinResult(
        width=width,
        height=height,
        tiles=len(parsed[2]) if parsed else len(_discover_tiles(folder)),
        discarded_pixels=width * height - used_pixels,
        pixel_sha256=digest,
        matches_original=matches,
        output_path=str(destination),
    )
