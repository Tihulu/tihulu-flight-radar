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

        # Prefer a stable loopback origin so per-browser receiver coordinates
        # stored in localStorage persist between app launches. If another
        # instance owns the port, fall back safely to a random local port.
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 8505), Handler)
        except OSError:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._lifecycle_lock = threading.Lock()
        self._started = False
        self._closed = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/"

    def start(self):
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("Local map listener is already closed.")
            if self._started:
                return
            self.thread.start()
            self._started = True

    def close(self):
        """Idempotently stop this app-owned listener and bounded server thread.

        BaseServer.shutdown() blocks forever if serve_forever was never started,
        so an unstarted instance needs server_close() only.
        """
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            started = self._started
        try:
            if started:
                self.httpd.shutdown()
        finally:
            self.httpd.server_close()
        if started:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise RuntimeError("App-owned local map server did not stop within 3 seconds.")
