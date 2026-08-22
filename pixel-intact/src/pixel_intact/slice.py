from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .completeness import load_intact_image


@dataclass(frozen=True)
class SliceTile:
    row: int
    col: int
    left: int
    top: int
    width: int
    height: int

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.left + self.width, self.top + self.height)

    @property
    def name(self) -> str:
        return f"r{self.row:02d}_c{self.col:02d}.png"


@dataclass(frozen=True)
class SlicePlan:
    source_width: int
    source_height: int
    rows: int
    cols: int
    tiles: tuple[SliceTile, ...]
    discarded_pixels: int
    remainder_distributed: bool

    @property
    def source_pixels(self) -> int:
        return self.source_width * self.source_height

    @property
    def exported_pixels(self) -> int:
        return sum(tile.width * tile.height for tile in self.tiles)

    @property
    def complete(self) -> bool:
        return self.discarded_pixels == 0 and self.exported_pixels == self.source_pixels


def _span_sizes(length: int, count: int) -> list[int]:
    if count < 1:
        raise ValueError("count must be at least 1")
    if length < count:
        raise ValueError(f"cannot split {length}px into {count} parts")
    base, extra = divmod(length, count)
    # First leftover columns/rows receive +1px so the original canvas stays complete.
    return [base + (1 if index < extra else 0) for index in range(count)]


def _offsets(sizes: list[int]) -> list[int]:
    origin = 0
    starts: list[int] = []
    for size in sizes:
        starts.append(origin)
        origin += size
    return starts


def plan_slice(
    width: int,
    height: int,
    *,
    cols: int | None = None,
    rows: int | None = None,
    tile_width: int | None = None,
    tile_height: int | None = None,
) -> SlicePlan:
    """Plan a lossless cut. Remainder pixels become extra tiles or extra width/height."""
    if (cols is None) != (rows is None):
        raise ValueError("cols and rows must be provided together")
    if (tile_width is None) != (tile_height is None):
        raise ValueError("tile_width and tile_height must be provided together")
    if (cols is None) == (tile_width is None):
        raise ValueError("choose either a grid (cols/rows) or a tile size")

    remainder_distributed = False
    if cols is not None and rows is not None:
        col_sizes = _span_sizes(width, cols)
        row_sizes = _span_sizes(height, rows)
        remainder_distributed = (width % cols) != 0 or (height % rows) != 0
    else:
        assert tile_width is not None and tile_height is not None
        if tile_width < 1 or tile_height < 1:
            raise ValueError("tile size must be at least 1px")
        col_sizes = []
        remaining = width
        while remaining > 0:
            size = min(tile_width, remaining)
            col_sizes.append(size)
            remaining -= size
        row_sizes = []
        remaining = height
        while remaining > 0:
            size = min(tile_height, remaining)
            row_sizes.append(size)
            remaining -= size

    col_origins = _offsets(col_sizes)
    row_origins = _offsets(row_sizes)
    tiles = [
        SliceTile(
            row=row_index,
            col=col_index,
            left=col_origins[col_index],
            top=row_origins[row_index],
            width=col_sizes[col_index],
            height=row_sizes[row_index],
        )
        for row_index, _ in enumerate(row_sizes)
        for col_index, _ in enumerate(col_sizes)
    ]
    exported = sum(tile.width * tile.height for tile in tiles)
    return SlicePlan(
        source_width=width,
        source_height=height,
        rows=len(row_sizes),
        cols=len(col_sizes),
        tiles=tuple(tiles),
        discarded_pixels=width * height - exported,
        remainder_distributed=remainder_distributed,
    )


def slice_image(
    path: str | Path,
    out_dir: str | Path,
    *,
    cols: int | None = None,
    rows: int | None = None,
    tile_width: int | None = None,
    tile_height: int | None = None,
) -> SlicePlan:
    image = load_intact_image(path)
    plan = plan_slice(
        image.width,
        image.height,
        cols=cols,
        rows=rows,
        tile_width=tile_width,
        tile_height=tile_height,
    )
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for tile in plan.tiles:
        crop = image.crop(tile.box)
        crop.save(destination / tile.name, format="PNG", compress_level=1)
    _write_manifest(destination, plan, Path(path).name)
    return plan


def _write_manifest(out_dir: Path, plan: SlicePlan, source_name: str) -> None:
    lines = [
        f"source={source_name}",
        f"width={plan.source_width}",
        f"height={plan.source_height}",
        f"rows={plan.rows}",
        f"cols={plan.cols}",
        f"discarded_pixels={plan.discarded_pixels}",
        f"complete={str(plan.complete).lower()}",
        "tiles=",
    ]
    for tile in plan.tiles:
        lines.append(
            f"{tile.name}:{tile.row},{tile.col},{tile.left},{tile.top},{tile.width},{tile.height}"
        )
    (out_dir / "intact-manifest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
