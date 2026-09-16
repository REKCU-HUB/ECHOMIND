"""Loopback-only HTTP bridge and static website for the EchoMind EEG demo."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from demo_engine import DemoEngine
from pointer_state import PointerState
from gaze_state import GazeState

MAX_BODY = 16 * 1024


class DemoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address=("127.0.0.1", 8765), engine=None, static_root=None):
        if server_address[0] != "127.0.0.1":
            raise ValueError("演示服务仅允许绑定 127.0.0.1")
        self.engine = engine or DemoEngine()
        self.pointer = PointerState()
        self.gaze = GazeState()
        self.static_root = Path(static_root or Path(__file__).parent / "web" / "dist").resolve()
        super().__init__(server_address, DemoHandler)


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "EchoMindDemo/1.0"

    def log_message(self, format, *args):
        # Suppress 4 Hz polling chatter. Host application may display exceptions.
        pass

    def _json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _valid_host(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host", "") == expected

    def _valid_origin(self):
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return origin == f"http://127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self._valid_host():
            return self._json(403, {"error": "仅允许本机演示地址"})
        path = urlsplit(self.path).path
        if path == "/api/gaze":
            if not self._valid_origin() or self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self._json(403, {"error": "Real gaze bridge is local and same-origin only"})
            return self._json(200, self.server.gaze.snapshot())
        if path == "/api/pointer":
            if not self._valid_origin() or self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self._json(403, {"error": "Pointer bridge is local and same-origin only"})
            consumer = parse_qs(urlsplit(self.path).query).get("viewer") == ["eye-demo"]
            return self._json(200, self.server.pointer.snapshot(consumer=consumer))
        if path in {"/api/health", "/serverhealth"}:
            return self._json(200, {"ok": True, "service": "echomind-eeg-demo", "simulated": True})
        if path == "/api/state":
            return self._json(200, self.server.engine.snapshot())
        if path.startswith("/api/"):
            return self._json(404, {"error": "接口不存在"})
        decoded = unquote(path)
        if "\x00" in decoded or "\\" in decoded:
            return self._json(400, {"error": "无效路径"})
        relative = decoded.lstrip("/") or "index.html"
        try:
            target = (self.server.static_root / relative).resolve()
            target.relative_to(self.server.static_root)
        except (ValueError, OSError):
            return self._json(403, {"error": "路径超出演示网站目录"})
        if target.is_dir():
            try:
                target = (target / "index.html").resolve()
                target.relative_to(self.server.static_root)
            except (ValueError, OSError):
                return self._json(403, {"error": "路径超出演示网站目录"})
        if not target.is_file():
            return self._json(404, {"error": "页面尚未构建或文件不存在"})
        try:
            raw = target.read_bytes()
        except OSError:
            return self._json(404, {"error": "无法读取页面"})
        mime = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.get(target.suffix.lower())
        mime = mime or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if not self._valid_host() or not self._valid_origin() or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self._json(403, {"error": "禁止其他网站修改本机演示状态"})
        path = urlsplit(self.path).path
        if path not in {"/api/event", "/api/config", "/api/pointer", "/api/gaze"}:
            return self._json(404, {"error": "接口不存在"})
        if self.headers.get("Transfer-Encoding"):
            return self._json(400, {"error": "不支持分块请求"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"error": "请求长度无效"})
        if length <= 0 or length > MAX_BODY:
            return self._json(413, {"error": "JSON 请求需小于 16 KB"})
        if self.headers.get_content_type() != "application/json":
            return self._json(415, {"error": "请发送 application/json"})
        try:
            self.connection.settimeout(3)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("请求不完整")
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON 需要是对象")
            if path == "/api/gaze":
                result = self.server.gaze.update(payload)
            elif path == "/api/pointer":
                result = self.server.pointer.update(payload)
            else:
                result = self.server.engine.event(payload) if path == "/api/event" else self.server.engine.configure(payload)
        except (ValueError, UnicodeError, TimeoutError) as exc:
            return self._json(400, {"error": str(exc)})
        return self._json(200, result)

    def do_OPTIONS(self):
        self._json(403, {"error": "演示接口不允许跨网站访问"})


def create_server(port=8765, engine=None, static_root=None):
    return DemoHTTPServer(("127.0.0.1", port), engine=engine, static_root=static_root)


def serve(port=8765, engine=None, static_root=None):
    server = create_server(port, engine, static_root)
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EchoMind local simulated EEG bridge")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--static-root", type=Path)
    args = parser.parse_args()
    serve(args.port, static_root=args.static_root)
