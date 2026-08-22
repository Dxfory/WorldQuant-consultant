from __future__ import annotations

import http.client
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from pixel_intact.studio import serve_studio


def _web_root() -> Path:
    return Path(__file__).resolve().parents[1] / "web"


def _multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = "----PixelIntactBoundary"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode() + b"\r\n")
    for name, (filename, data) in files.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        chunks.append(b"Content-Type: image/png\r\n\r\n")
        chunks.append(data + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def test_studio_health_and_enhance() -> None:
    server = serve_studio(_web_root(), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        health = http.client.HTTPConnection(host, port, timeout=5)
        health.request("GET", "/api/health")
        response = health.getresponse()
        body = response.read().decode()
        health.close()
        assert response.status == 200
        assert '"lanczos": true' in body

        image = Image.new("RGB", (16, 10), (20, 40, 60))
        raw = BytesIO()
        image.save(raw, format="PNG")
        payload, content_type = _multipart(
            {"scale": "2", "clarity": "0", "sharpness": "0", "engine": "lanczos"},
            {"image": ("tiny.png", raw.getvalue())},
        )
        conn = http.client.HTTPConnection(host, port, timeout=10)
        conn.request("POST", "/api/enhance", body=payload, headers={"Content-Type": content_type})
        enhanced = conn.getresponse()
        data = enhanced.read()
        conn.close()
        assert enhanced.status == 200
        result = Image.open(BytesIO(data))
        assert result.size == (32, 20)
    finally:
        server.shutdown()
        server.server_close()
