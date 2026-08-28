from __future__ import annotations

import json
from email import message_from_bytes
from email.policy import default as email_default
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from .enhance import EnhanceSettings, enhance_pil, output_exceeds
from .safety import open_local_image
from .export import encode_png
from .slice import plan_slice
from .superres import fsr_available

MAX_UPLOAD = 120 * 1024 * 1024


class StudioHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/health":
            self._json(
                200,
                {
                    "ok": True,
                    "engine": {"lanczos": True, "fsr": fsr_available()},
                },
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            fields, files = self._multipart()
        except ValueError as error:
            self._text(400, str(error))
            return
        if path == "/api/enhance":
            self._enhance(fields, files)
            return
        if path == "/api/slice":
            self._slice(fields, files)
            return
        self._text(404, "unknown api")

    def log_message(self, format: str, *args: object) -> None:
        if str(args[0]).startswith("GET /api") or str(args[0]).startswith("POST /api"):
            super().log_message(format, *args)

    def _multipart(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("empty upload")
        if length > MAX_UPLOAD:
            raise ValueError("上传切块太大，请改用更多行列，或先把原图切小再提高清晰度。")
        body = self.rfile.read(length)
        preamble = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
        message = message_from_bytes(preamble + body, policy=email_default)
        fields: dict[str, str] = {}
        files: dict[str, tuple[str, bytes]] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                files[str(name)] = (filename, payload)
            else:
                fields[str(name)] = payload.decode("utf-8", errors="replace")
        return fields, files

    def _open_image(self, files: dict[str, tuple[str, bytes]]) -> Image.Image:
        if "image" not in files:
            raise ValueError("缺少图片")
        return open_local_image(BytesIO(files["image"][1]))

    def _settings(self, fields: dict[str, str]) -> EnhanceSettings:
        return EnhanceSettings(
            scale=float(fields.get("scale", "2") or 2),
            clarity=float(fields.get("clarity", "0.35") or 0.35),
            sharpness=float(fields.get("sharpness", "0.85") or 0.85),
            engine=fields.get("engine", "lanczos") or "lanczos",
            denoise=fields.get("denoise", "") in {"1", "true", "on"},
        )

    def _enhance(self, fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> None:
        try:
            image = self._open_image(files)
            result = enhance_pil(image, self._settings(fields))
        except Exception as error:
            self._text(400, str(error))
            return
        payload = encode_png(result)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("X-Output-Width", str(result.width))
        self.send_header("X-Output-Height", str(result.height))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _slice(self, fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> None:
        try:
            image = self._open_image(files)
            settings = self._settings(fields)
            should_enhance = settings.scale != 1 or settings.engine == "fsr"
            if should_enhance and not output_exceeds(image.width, image.height, settings.scale):
                image = enhance_pil(image, settings)
            cols = int(fields["cols"]) if fields.get("cols") else None
            rows = int(fields["rows"]) if fields.get("rows") else None
            tile_width = int(fields["tile_width"]) if fields.get("tile_width") else None
            tile_height = int(fields["tile_height"]) if fields.get("tile_height") else None
            plan = plan_slice(
                image.width,
                image.height,
                cols=cols,
                rows=rows,
                tile_width=tile_width,
                tile_height=tile_height,
            )
        except Exception as error:
            self._text(400, str(error))
            return
        self._json(
            200,
            {
                "width": plan.source_width,
                "height": plan.source_height,
                "rows": plan.rows,
                "cols": plan.cols,
                "complete": plan.complete,
                "discarded_pixels": plan.discarded_pixels,
                "exported_pixels": plan.exported_pixels,
            },
        )

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_studio(web_root: Path, port: int) -> ThreadingHTTPServer:
    handler = partial(StudioHandler, directory=str(web_root))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


__all__ = ["StudioHandler", "serve_studio"]
