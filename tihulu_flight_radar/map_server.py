"""Local-only HTTP viewer: no uploaded data, no fabricated positions."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files


class LocalMapServer:
    def __init__(self, getter):
        self.getter = getter
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.split("?", 1)[0] == "/":
                    data = files("tihulu_flight_radar").joinpath("map.html").read_bytes()
                    kind = "text/html; charset=utf-8"
                elif self.path.split("?", 1)[0] == "/map_focus.js":
                    data = files("tihulu_flight_radar").joinpath("map_focus.js").read_bytes()
                    kind = "application/javascript; charset=utf-8"
                elif self.path.split("?", 1)[0] == "/api/aircraft":
                    snapshot = owner.getter()
                    data = json.dumps(snapshot if snapshot is not None else {
                        "aircraft": [], "error": "No live receiver data available."
                    }, allow_nan=False).encode("utf-8")
                    kind = "application/json; charset=utf-8"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                 "style-src 'self' 'unsafe-inline'; img-src 'self' https://tile.openstreetmap.org data:; "
                                 "connect-src 'self'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, _format, *_args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/"

    def start(self):
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
