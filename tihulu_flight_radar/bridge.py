"""Read-only-by-default local bridge for GitHub Pages and local browsers.

Standalone Python standard-library server. The GitHub Pages site is static:
all RTL-SDR/readsb access is performed by this locally installed companion.
"""
from __future__ import annotations

import argparse
import json
import math
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .control import ReceiverController
from .core import DataError, position_is_fresh, recently_seen

GERMANY = (51.1657, 10.4515)
MAX_BODY = 2048
MAX_ONLINE_BYTES = 4_194_304
ONLINE_CACHE_SECONDS = 35
STATIC_DIR = Path(__file__).resolve().parent / "web"


def _coord(value: str | None, fallback: float, low: float, high: float) -> float:
    if value is None:
        return fallback
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DataError("Invalid map coordinate.") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise DataError("Map coordinate out of bounds.")
    return result


def _icao(aircraft: dict) -> str | None:
    value = aircraft.get("hex")
    if isinstance(value, str) and len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return value.lower()
    return None


def merge_aircraft(local: list[dict], online: list[dict]) -> list[dict]:
    """Prefer real local fields; combine only provably matching ICAO24 identities."""
    merged: list[dict] = []
    by_icao: dict[str, dict] = {}
    for label, source in (("antenna", local), ("internet", online)):
        for aircraft in source:
            if not isinstance(aircraft, dict) or not recently_seen(aircraft):
                continue
            key = _icao(aircraft)
            prior = by_icao.get(key) if key else None
            if prior is not None:
                prior["sources"].append(label)
                prior["observations"][label] = aircraft
                if not position_is_fresh(prior) and position_is_fresh(aircraft):
                    # The displayed position's source remains independently attributable.
                    prior["lat"], prior["lon"] = aircraft["lat"], aircraft["lon"]
                    prior["seen_pos"] = aircraft["seen_pos"]
                    prior["position_source"] = label
                continue
            row = dict(aircraft)
            row["sources"] = [label]
            row["observations"] = {label: aircraft}
            row["position_source"] = label if position_is_fresh(aircraft) else None
            merged.append(row)
            if key is not None:
                by_icao[key] = row
    return merged


class DataProvider:
    """Bounds anonymous public API traffic; errors never become fake positions."""
    def __init__(self):
        self.lock = threading.Lock()
        self.cache_key: tuple | None = None
        self.cached: list[dict] = []
        self.last_update: float | None = None
        self.retry_after = 0.0
        self.last_error: str | None = None

    def fetch(self, lat: float, lon: float, radius: int) -> tuple[list[dict], dict]:
        key = (round(lat, 1), round(lon, 1), radius)
        with self.lock:
            current = time.monotonic()
            if self.cache_key == key and current < self.retry_after:
                return list(self.cached), self._status(cached=True)
            if current < self.retry_after and self.cache_key != key:
                return [], self._status(cached=True)
            self.cache_key = key
            self.cached = []
            self.last_error = None
            self.retry_after = current + ONLINE_CACHE_SECONDS
            url = f"https://api.adsb.lol/v2/point/{lat:.3f}/{lon:.3f}/{radius}"
            request = Request(url, headers={
                "Accept": "application/json", "User-Agent": "TihuluFlightRadar/0.3.1 (local bridge)"
            })
            # Prevent localhost HTTP proxies and unbounded downloads.
            try:
                opener = build_opener(ProxyHandler({}))
                with opener.open(request, timeout=6) as response:
                    raw = response.read(MAX_ONLINE_BYTES + 1)
                if len(raw) > MAX_ONLINE_BYTES:
                    raise DataError("Online aircraft response too large.")
                result = json.loads(raw)
                if not isinstance(result, dict) or not isinstance(result.get("ac"), list):
                    raise DataError("Invalid online aircraft response.")
                self.cached = [a for a in result["ac"][:10000]
                               if isinstance(a, dict) and recently_seen(a)]
                self.last_update = time.time()
            except HTTPError as exc:
                self.last_error = f"Provider HTTP {exc.code}"
                if exc.code == 429:
                    raw_wait = exc.headers.get("Retry-After", "90")
                    try:
                        wait = max(60, min(3600, int(raw_wait)))
                    except ValueError:
                        wait = 90
                    self.retry_after = time.monotonic() + wait
            except (URLError, OSError, ValueError, DataError) as exc:
                self.last_error = str(exc)[:180]
            return list(self.cached), self._status(cached=False)

    def _status(self, cached: bool) -> dict:
        return {"provider": "adsb.lol", "attribution": "adsb.lol — ODbL 1.0",
                "updated_at": self.last_update if self.cached else None,
                "error": self.last_error, "cached": cached}


class Bridge:
    def __init__(self, *, token: str | None = None, allow_control: bool = False):
        self.token = token or secrets.token_urlsafe(32)
        self.allow_control = allow_control
        self.receiver = ReceiverController()
        self.receiver_lock = threading.RLock()
        self.online = DataProvider()

    def snapshot(self, mode: str, lat: float, lon: float, radius: int) -> dict:
        if mode not in ("antenna", "internet", "hybrid", "auto"):
            raise DataError("Unknown source mode.")
        local: list[dict] = []
        online: list[dict] = []
        local_status: dict = {"state": "disabled", "error": None}
        online_status: dict = {"state": "disabled", "error": None}
        want_local = mode in ("antenna", "hybrid", "auto")
        want_online = mode in ("internet", "hybrid")
        if want_local:
            try:
                with self.receiver_lock:
                    data = self.receiver.snapshot()
                local = [a for a in data.get("aircraft", []) if isinstance(a, dict) and recently_seen(a)]
                local_status = {"state": "receiving" if local else "no_aircraft",
                                "error": None, "messages": data.get("messages"),
                                "now": data.get("now")}
            except DataError as exc:
                local_status = {"state": "unavailable", "error": str(exc)}
        if mode == "auto" and not local:
            want_online = True
        if want_online:
            online, online_status = self.online.fetch(lat, lon, radius)
            online_status["state"] = "unavailable" if online_status.get("error") else "available"
        active_sources = (["antenna"] if want_local else []) + (["internet"] if want_online else [])
        return {"mode": mode, "active_sources": active_sources, "generated_at": time.time(),
                "aircraft": merge_aircraft(local, online),
                "counts": {"antenna": len(local), "internet": len(online),
                           "combined": len(merge_aircraft(local, online))},
                "sources": {"antenna": local_status, "internet": online_status}}

    def receiver_state(self) -> dict:
        with self.receiver_lock:
            active, detail = self.receiver.status()
            return {"active": active, "detail": detail, "mode": self.receiver.mode,
                    "control_enabled": self.allow_control}

    def control(self, action: str) -> str:
        if not self.allow_control:
            raise DataError("Hardware controls are disabled; launch with --allow-control to enable.")
        with self.receiver_lock:
            if action == "start":
                return self.receiver.start()
            if action == "stop":
                return self.receiver.stop()
            if action == "restart":
                return self.receiver.restart()
        raise DataError("Unsupported receiver action.")


def make_handler(bridge: Bridge, port: int):
    allowed = {"https://tihulu.github.io",
               f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "TihuluBridge/0.1"

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin in allowed

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in hosts

        def _headers(self, code: int, type_: str, length: int):
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            origin = self.headers.get("Origin")
            if origin in allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()

        def _send(self, code: int, data: dict):
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self._headers(code, "application/json; charset=utf-8", len(raw))
            self.wfile.write(raw)

        def _authorized(self):
            return secrets.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + bridge.token
            )

        def _guard(self) -> bool:
            if not self._host_ok() or not self._origin_ok():
                self._send(HTTPStatus.FORBIDDEN, {"error": "Untrusted host or origin."})
                return False
            return True

        def do_OPTIONS(self):
            if not self._guard():
                return
            origin = self.headers.get("Origin")
            if origin not in allowed:
                self._send(HTTPStatus.FORBIDDEN, {"error": "Origin not allowed."})
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_GET(self):
            if not self._guard():
                return
            path = urlsplit(self.path)
            if path.path in ("/", "/index.html", "/app.js", "/style.css"):
                name = "index.html" if path.path == "/" else path.path[1:]
                file = STATIC_DIR / name
                if not file.is_file():
                    self._send(HTTPStatus.NOT_FOUND, {"error": "Web asset missing."})
                    return
                raw = file.read_bytes()
                mime = "text/html" if name.endswith(".html") else (
                    "text/javascript" if name.endswith(".js") else "text/css")
                self._headers(HTTPStatus.OK, mime + "; charset=utf-8", len(raw))
                self.wfile.write(raw)
                return
            if not path.path.startswith("/api/"):
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "Enter the pairing token shown in the bridge terminal."})
                return
            if path.path == "/api/status":
                self._send(HTTPStatus.OK, bridge.receiver_state())
                return
            if path.path != "/api/aircraft":
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            try:
                query = parse_qs(path.query)
                one = lambda name, default: query.get(name, [default])[0]
                mode = one("mode", "auto")
                lat = _coord(one("lat", None), GERMANY[0], -90, 90)
                lon = _coord(one("lon", None), GERMANY[1], -180, 180)
                radius = int(one("radius", "100"))
                if not 10 <= radius <= 250:
                    raise DataError("Radius must be 10–250 nautical miles.")
                self._send(HTTPStatus.OK, bridge.snapshot(mode, lat, lon, radius))
            except (DataError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def do_POST(self):
            if not self._guard():
                return
            if urlsplit(self.path).path != "/api/control":
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "Pairing token required."})
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 1 <= n <= MAX_BODY:
                    raise DataError("Invalid request length.")
                body = json.loads(self.rfile.read(n))
                if not isinstance(body, dict) or body.get("action") not in ("start", "stop", "restart"):
                    raise DataError("Invalid receiver action.")
                self._send(HTTPStatus.OK, {"message": bridge.control(body["action"])})
            except (DataError, ValueError, UnicodeError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Tihulu Flight Radar local browser companion")
    parser.add_argument("--port", type=int, default=8510)
    parser.add_argument("--allow-control", action="store_true",
                        help="Explicitly permit authenticated Start/Stop/Restart from the browser")
    parser.add_argument("--open-browser", action="store_true",
                        help="Open the local web UI automatically after launching the bridge")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    bridge = Bridge(allow_control=args.allow_control)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bridge, args.port))
    print(f"Local radar UI: http://127.0.0.1:{args.port}/", flush=True)
    print(f"Bridge URL: http://127.0.0.1:{args.port}", flush=True)
    print(f"Session pairing token: {bridge.token}", flush=True)
    print("Keep this token private. Bridge is loopback-only; receiver controls:",
          "enabled" if args.allow_control else "disabled", flush=True)
    if args.open_browser:
        import webbrowser
        # The desktop launcher uses Terminal=true so the pairing token remains
        # visible to the owner. Never encode a token into a URL.
        threading.Thread(
            target=lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/"),
            daemon=True,
        ).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        bridge.receiver.close()


if __name__ == "__main__":
    main()
