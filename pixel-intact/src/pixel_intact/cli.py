from __future__ import annotations

import argparse
import json
from pathlib import Path
import webbrowser

from .batch import batch_enhance
from .completeness import inspect_image
from .enhance import EnhanceSettings, enhance_image
from .join import join_tiles
from .slice import slice_image
from .studio import serve_studio
from .superres import fsr_available


def _print_report(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pixel-intact",
        description="Keep every original pixel, then cut, reconstruct, or raise clarity.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = sub.add_parser("inspect", help="Report original size and completeness")
    inspect_cmd.add_argument("image")

    slice_cmd = sub.add_parser("slice", help="Losslessly cut an image; remainder pixels are kept")
    slice_cmd.add_argument("image")
    slice_cmd.add_argument("--out", required=True, help="Output folder for PNG tiles")
    slice_cmd.add_argument("--cols", type=int)
    slice_cmd.add_argument("--rows", type=int)
    slice_cmd.add_argument("--tile-width", type=int)
    slice_cmd.add_argument("--tile-height", type=int)
    slice_cmd.add_argument("--scale", type=float, default=1.0, help="Enhance/upscale before cutting")
    slice_cmd.add_argument("--clarity", type=float, default=0.35)
    slice_cmd.add_argument("--sharpness", type=float, default=0.85)
    slice_cmd.add_argument("--engine", choices=("lanczos", "fsr"), default="lanczos")

    join_cmd = sub.add_parser("join", help="Reassemble tiles into the complete original")
    join_cmd.add_argument("tiles", help="Folder that contains rXX_cXX.png tiles")
    join_cmd.add_argument("--out", required=True)
    join_cmd.add_argument("--original", help="Optional original file to verify pixel equality")

    enhance_cmd = sub.add_parser("enhance", help="Lanczos upscale plus clarity / sharpen")
    enhance_cmd.add_argument("image")
    enhance_cmd.add_argument("--out", required=True)
    enhance_cmd.add_argument("--scale", type=float, default=2.0)
    enhance_cmd.add_argument("--clarity", type=float, default=0.28)
    enhance_cmd.add_argument("--sharpness", type=float, default=0.85)
    enhance_cmd.add_argument("--engine", choices=("lanczos", "fsr"), default="lanczos")
    enhance_cmd.add_argument("--denoise", action="store_true")
    enhance_cmd.add_argument("--autocontrast", action="store_true")
    enhance_cmd.add_argument("--contrast", type=float, default=1.0)

    batch_cmd = sub.add_parser("batch", help="Enhance every image in a folder")
    batch_cmd.add_argument("folder")
    batch_cmd.add_argument("--out", required=True)
    batch_cmd.add_argument("--scale", type=float, default=2.0)
    batch_cmd.add_argument("--clarity", type=float, default=0.35)
    batch_cmd.add_argument("--sharpness", type=float, default=0.85)
    batch_cmd.add_argument("--engine", choices=("lanczos", "fsr"), default="lanczos")
    batch_cmd.add_argument("--format", dest="fmt", choices=("png", "jpeg", "webp"), default="png")

    studio_cmd = sub.add_parser("studio", help="Open the local high-fidelity web studio")
    studio_cmd.add_argument("--port", type=int, default=8765)
    studio_cmd.add_argument("--no-browser", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "inspect":
        report = inspect_image(args.image)
        _print_report(
            {
                "path": report.path,
                "format": report.format,
                "mode": report.mode,
                "width": report.width,
                "height": report.height,
                "pixels": report.pixels,
                "has_alpha": report.has_alpha,
                "dpi": report.dpi,
                "pixel_sha256": report.pixel_sha256,
                "complete_canvas": report.is_complete_canvas,
            }
        )
        return 0

    if args.command == "slice":
        enhance = None
        if args.scale != 1:
            enhance = EnhanceSettings(
                scale=args.scale,
                clarity=args.clarity,
                sharpness=args.sharpness,
                engine=args.engine,
            )
        plan = slice_image(
            args.image,
            args.out,
            cols=args.cols,
            rows=args.rows,
            tile_width=args.tile_width,
            tile_height=args.tile_height,
            enhance=enhance,
        )
        _print_report(
            {
                "width": plan.source_width,
                "height": plan.source_height,
                "rows": plan.rows,
                "cols": plan.cols,
                "tiles": len(plan.tiles),
                "source_pixels": plan.source_pixels,
                "exported_pixels": plan.exported_pixels,
                "discarded_pixels": plan.discarded_pixels,
                "complete": plan.complete,
                "remainder_distributed": plan.remainder_distributed,
                "out": str(Path(args.out).resolve()),
            }
        )
        return 0

    if args.command == "join":
        result = join_tiles(args.tiles, args.out, original_path=args.original)
        _print_report(
            {
                "width": result.width,
                "height": result.height,
                "tiles": result.tiles,
                "discarded_pixels": result.discarded_pixels,
                "complete": result.complete,
                "matches_original": result.matches_original,
                "pixel_sha256": result.pixel_sha256,
                "out": result.output_path,
            }
        )
        return 0

    if args.command == "studio":
        here = Path(__file__).resolve()
        candidates = [
            here.parents[2] / "web",
            Path.cwd() / "pixel-intact" / "web",
            Path.cwd() / "web",
        ]
        web_root = next((path for path in candidates if (path / "index.html").exists()), None)
        if web_root is None:
            raise SystemExit("cannot find web/index.html; run from the pixel-intact checkout")
        server = serve_studio(web_root, args.port)
        url = f"http://127.0.0.1:{args.port}/"
        print(f"Pixel Intact studio: {url}")
        print(f"local engine: lanczos=yes  fsr={'yes' if fsr_available() else 'no'}")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nstudio stopped")
        return 0

    if args.command == "batch":
        written = batch_enhance(
            args.folder,
            args.out,
            EnhanceSettings(
                scale=args.scale,
                clarity=args.clarity,
                sharpness=args.sharpness,
                engine=args.engine,
            ),
            fmt=args.fmt,
        )
        _print_report({"count": len(written), "out": str(Path(args.out).resolve())})
        return 0

    enhance_image(
        args.image,
        args.out,
        EnhanceSettings(
            scale=args.scale,
            clarity=args.clarity,
            sharpness=args.sharpness,
            denoise=args.denoise,
            autocontrast=args.autocontrast,
            contrast=args.contrast,
            engine=args.engine,
        ),
    )
    report = inspect_image(args.out)
    _print_report(
        {
            "width": report.width,
            "height": report.height,
            "pixels": report.pixels,
            "out": str(Path(args.out).resolve()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
