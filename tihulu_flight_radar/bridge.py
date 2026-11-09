"""Read-only-by-default local bridge for GitHub Pages and local browsers.

Standalone Python standard-library server. The GitHub Pages site is static:
all RTL-SDR/readsb access is performed by this locally installed companion.
"""
from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
import secrets
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit, unquote
from urllib.request import ProxyHandler, Request, build_opener

from .network_sources import MultiNetworkProvider, parse_provider_selection
from .control import ReceiverController
from .rf_history_store import RFHistoryStore
from .core import DataError, position_is_fresh, recently_seen
from .offline_maps import (MAP_ROOT, MAX_MAP_BYTES, SAFE_NAME, discover,
                           metadata as map_metadata, read_tile, select as select_offline_map)

GERMANY = (51.1657, 10.4515)
MAX_BODY = 2048
MAX_ONLINE_BYTES = 4_194_304
ONLINE_CACHE_SECONDS = 35
STATIC_DIR = Path(__file__).resolve().parent / "web"
# The bundled upstream tar1090 frontend is installed into a user-owned cache.
# This lets the complete map work offline and with no SDR/readsb service.
# Never mutate that directory in a request handler or start an SDR from it.
TAR_CACHE_DIR = Path.home() / ".local/share/tihulu-flight-radar/tar1090"


def tar_asset_path(raw_path: str, roots: tuple[Path, ...] | None = None) -> Path | None:
    """Resolve ONLY regular files below an installed tar1090 static directory.

    Reject traversal, encoded separators, symlink escapes, absolute paths and
    unknown paths; only user-local static files are served, never arbitrary
    home-directory contents or bridge pairing secrets.
    """
    if not raw_path.startswith("/tar1090/"):
        return None
    relative = unquote(raw_path[len("/tar1090/"):])
    if not relative or relative.endswith("/"):
        relative += "index.html"
    if (relative.startswith("/") or "\\" in relative or "\x00" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        return None
    for root in roots or (TAR_CACHE_DIR, STATIC_DIR / "tar1090"):
        root = root.resolve()
        candidate = (root / relative).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return candidate
    return None



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


def validate_search_place(value: object) -> dict:
    """Strict small WGS84 map *search* preference; never SDR site metadata."""
    if not isinstance(value, dict):
        raise DataError("Invalid saved map search location.")
    lat, lon, radius = value.get("lat"), value.get("lon"), value.get("radius")
    if (not isinstance(lat, (int, float)) or isinstance(lat, bool)
            or not isinstance(lon, (int, float)) or isinstance(lon, bool)
            or not math.isfinite(lat) or not math.isfinite(lon)
            or abs(lat) > 90 or abs(lon) > 180
            or type(radius) is not int or radius not in (25, 50, 100, 150, 250)):
        raise DataError("Invalid saved map coordinates or radius.")
    place = {"lat": float(lat), "lon": float(lon), "radius": radius, "zoom": 9}
    for name, max_chars in (("label", 190), ("name", 100),
                            ("region", 100), ("country", 10), ("provider", 35)):
        raw = value.get(name, "")
        if not isinstance(raw, str) or len(raw) > max_chars or any(
                ord(c) < 32 for c in raw):
            raise DataError("Invalid map location label.")
        place[name] = raw.strip()
    if not place["label"]:
        raise DataError("Saved map location needs a display label.")
    if place["country"] not in ("", "DE", "TR", "all"):
        raise DataError("Invalid map country.")
    return place


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
                if label == "internet":
                    prior["internet_providers"] = list(aircraft.get("internet_providers", []))
                    if isinstance(aircraft.get("observations"), dict):
                        networks = aircraft["observations"].get("internet_sources")
                        if isinstance(networks, dict):
                            prior["observations"]["internet_sources"] = networks
                if not position_is_fresh(prior) and position_is_fresh(aircraft):
                    # The displayed position's source remains independently attributable.
                    prior["lat"], prior["lon"] = aircraft["lat"], aircraft["lon"]
                    prior["seen_pos"] = aircraft["seen_pos"]
                    prior["position_source"] = label
                continue
            row = dict(aircraft)
            row["sources"] = [label]
            row["observations"] = {label: aircraft}
            if label == "internet" and isinstance(aircraft.get("observations"), dict):
                networks = aircraft["observations"].get("internet_sources")
                if isinstance(networks, dict):
                    row["observations"]["internet_sources"] = networks
            row["position_source"] = label if position_is_fresh(aircraft) else None
            merged.append(row)
            if key is not None:
                by_icao[key] = row
    return merged


class DataProvider:
    """Personal, low-rate public feed client with source-aware failover.

    Never mix network feed data into real RF message counters. adsb.fi is a
    personal/non-commercial fallback with explicit attribution requirements.
    """
    FEEDS = (
        ("adsb.lol", "https://api.adsb.lol/v2/point/{lat}/{lon}/{r}",
         "adsb.lol — ODbL 1.0"),
        ("adsb.fi", "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{r}",
         "adsb.fi — personal/non-commercial; cite adsb.fi"),
    )

    def __init__(self):
        self.lock = threading.Lock()
        self.cache_key = None
        self.cached: list[dict] = []
        self.last_update: float | None = None
        self.retry_after = 0.0
        self.backoff: dict[str, float] = {}
        self.last_error: str | None = None
        self.provider_name = "adsb.lol"
        self.attribution = "adsb.lol — ODbL 1.0"

    def _fresh_cached(self) -> list[dict]:
        """Age each real observation while in cache; never freeze seen=0."""
        if self.last_update is None:
            return []
        elapsed = max(0.0, time.time() - self.last_update)
        result = []
        for aircraft in self.cached:
            row = dict(aircraft)
            for age_field in ("seen", "seen_pos"):
                age = row.get(age_field)
                if isinstance(age, (float, int)) and math.isfinite(age):
                    row[age_field] = max(0.0, float(age)) + elapsed
            if recently_seen(row):
                result.append(row)
        return result

    def _status(self, cached: bool) -> dict:
        age = max(0.0, time.time() - self.last_update) if self.last_update else None
        return {"provider": self.provider_name, "attribution": self.attribution,
                "updated_at": self.last_update, "cache_age_seconds": age,
                "error": self.last_error, "cached": cached}

    def fetch(self, lat: float, lon: float, radius: int) -> tuple[list[dict], dict]:
        key = (round(lat, 1), round(lon, 1), radius)
        with self.lock:
            current = time.monotonic()
            if current < self.retry_after:
                if self.cache_key == key:
                    return self._fresh_cached(), self._status(cached=True)
                return [], {"provider": self.provider_name,
                            "attribution": self.attribution, "updated_at": None,
                            "error": "Feed refresh cooldown; use Refresh later.",
                            "cached": True}

            if key != self.cache_key:
                # Never show cached aircraft from a different search area.
                self.cached = []
                self.last_update = None
            self.cache_key = key
            self.last_error = None
            self.retry_after = current + ONLINE_CACHE_SECONDS
            errors: list[str] = []
            for name, template, attribution in self.FEEDS:
                if current < self.backoff.get(name, 0):
                    errors.append(name + ": cooldown")
                    continue
                url = template.format(lat=f"{lat:.3f}", lon=f"{lon:.3f}", r=radius)
                request = Request(url, headers={
                    "Accept": "application/json",
                    "User-Agent": "TihuluFlightRadar/0.3.1 (personal receiver application)"
                })
                try:
                    opener = build_opener(ProxyHandler({}))
                    # Two provider attempts must fit within the browser's
                    # 10-second request timeout; otherwise the frontend
                    # clears a healthy map because it aborts a slow response.
                    with opener.open(request, timeout=3.5) as response:
                        raw = response.read(MAX_ONLINE_BYTES + 1)
                    if len(raw) > MAX_ONLINE_BYTES:
                        raise DataError("Online feed response too large.")
                    result = json.loads(raw)
                    if not isinstance(result, dict) or not isinstance(result.get("ac"), list):
                        raise DataError("Invalid aircraft feed response schema.")
                    self.cached = [
                        aircraft for aircraft in result["ac"][:10000]
                        if isinstance(aircraft, dict) and recently_seen(aircraft)
                    ]
                    self.provider_name = name
                    self.attribution = attribution
                    self.last_update = time.time()
                    return list(self.cached), self._status(cached=False)
                except HTTPError as exc:
                    detail = f"{name}: HTTP {exc.code}"
                    errors.append(detail)
                    retry_header = exc.headers.get("Retry-After", "90")
                    try:
                        delay = int(retry_header)
                    except (ValueError, TypeError):
                        delay = 90
                    self.backoff[name] = time.monotonic() + (
                        max(60, min(3600, delay)) if exc.code == 429 else 90
                    )
                except (URLError, OSError, ValueError, DataError) as exc:
                    errors.append(f"{name}: {str(exc)[:95]}")
                    self.backoff[name] = time.monotonic() + 60
            self.last_error = " | ".join(errors) or "No feed available."
            # Preserve last *real* positions only for their remaining
            # freshness window, with age counters incremented accordingly.
            # Do not fabricate a new observation timestamp after an outage.
            return self._fresh_cached(), self._status(cached=bool(self.cached))


class Bridge:
    def __init__(self, *, token: str | None = None, allow_control: bool = False):
        self.token = token or secrets.token_urlsafe(32)
        self.allow_control = allow_control
        self.receiver = ReceiverController()
        self.receiver_lock = threading.RLock()
        self.online = DataProvider()
        self.multi_online = MultiNetworkProvider()
        self.last_start_error: str | None = None
        self._place_lock = threading.Lock()
        self.offline_map_name: str | None = None
        self.offline_map_path: Path | None = None
        self.rf_history = RFHistoryStore()
        # Native Qt uses an ephemeral loopback port; browser localStorage
        # changes origin on each launch. This owner-only settings file retains
        # the selected SEARCH region across ports, OS restarts and platforms.
        self._place_path = (Path.home() / ".config" / "tihulu-flight-radar"
                            / "map-search-location.json")

    def get_saved_search_place(self) -> dict | None:
        with self._place_lock:
            try:
                if not self._place_path.is_file() or self._place_path.stat().st_size > 2048:
                    return None
                return validate_search_place(json.loads(
                    self._place_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, DataError, UnicodeError):
                return None

    def save_search_place(self, raw: object) -> dict:
        place = validate_search_place(raw)
        with self._place_lock:
            self._place_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self._place_path.with_name(
                self._place_path.name+"."+secrets.token_hex(6)+".tmp")
            try:
                with tmp.open("x", encoding="utf-8") as fh:
                    json.dump(place, fh, ensure_ascii=False, allow_nan=False)
                tmp.chmod(0o600)
                tmp.replace(self._place_path)
            finally:
                tmp.unlink(missing_ok=True)
        return place

    def snapshot(self, mode: str, lat: float, lon: float, radius: int,
                 networks: tuple[str, ...] | None = None) -> dict:
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
                # Only receiver-origin rows, never merged Internet positions.
                if self.rf_history.enabled:
                    self.rf_history.append(local)
                count = data.get("messages")
                # A live readsb process writing aircraft.json may be decoding
                # zero radio frames. Keep this distinct from "receiving".
                local_state = ("receiving" if local else
                               "decoder_no_rf_messages" if count == 0 else
                               "no_recent_aircraft")
                local_status = {"state": local_state,
                                "error": None, "messages": count,
                                "now": data.get("now"),
                                "note": ("Decoder running, but no ADS-B messages have been decoded. "
                                         "Verify that the Nooelec SDR is owned by readsb, "
                                         "the 1090 MHz antenna is connected, and check "
                                         "journalctl -u readsb -n 40 --no-pager")
                                        if count == 0 else None}
            except DataError as exc:
                # Distinguish a genuinely stopped decoder from a running
                # decoder that has not written its first aircraft.json yet.
                # The latter can occur briefly during receiver startup.
                with self.receiver_lock:
                    active, detail = self.receiver.status()
                if self.receiver.mode != "Remote JSON" and not active:
                    local_status = {
                        "state": "decoder_stopped",
                        "error": detail + ". Start the local receiver in Flight Radar "
                                 "or use systemctl start readsb.service.",
                    }
                elif str(exc) == "Receiver data file not found.":
                    local_status = {
                        "state": "decoder_waiting_for_json",
                        "error": "Decoder is active, but aircraft.json has not been "
                                 "created at the configured readsb path yet. "
                                 "Check journalctl -u readsb.service and the readsb "
                                 "JSON output directory.",
                    }
                else:
                    local_status = {"state": "unavailable", "error": str(exc)}
        if mode == "auto" and not any(position_is_fresh(a) for a in local):
            want_online = True
        if want_online:
            online, online_status = (
                self.online.fetch(lat, lon, radius) if networks is None
                else self.multi_online.fetch(lat, lon, radius, networks)
            )
            online_status["state"] = "unavailable" if online_status.get("error") else "available"
        active_sources = (["antenna"] if want_local else []) + (["internet"] if want_online else [])
        return {"mode": mode, "active_sources": active_sources, "generated_at": time.time(),
                "aircraft": merge_aircraft(local, online),
                "counts": {"antenna": len(local), "internet": len(online),
                           "combined": len(merge_aircraft(local, online))},
                "sources": {"antenna": local_status, "internet": online_status}}

    def tar1090_status(self) -> dict:
        """Only report a local tar1090 with recent genuine decoder JSON.

        A served HTML page alone is not a working tar1090 receiver. This
        check never starts, stops or retunes an RTL-SDR.
        """
        from .core import find_tar1090_url
        url = find_tar1090_url()
        return {
            "available": bool(url),
            "url": url,
            "reason": None if url else (
                "No independent live readsb aircraft.json backend for tar1090. "
                "If this browser owns the single RTL-SDR via WebUSB, use "
                "Full radar map here instead; do not start readsb concurrently."
            )
        }

    def receiver_state(self) -> dict:
        with self.receiver_lock:
            active, detail = self.receiver.status()
            return {"active": active, "detail": detail, "mode": self.receiver.mode,
                    "control_enabled": self.allow_control,
                    "startup_error": self.last_start_error}

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
            # OSM volunteer tiles require a valid Referer and caching; no-referrer
            # caused the user's screenshot's striped '403 Access blocked' tiles.
            # strict-origin does not reveal local URL paths or pairing secrets.
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
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
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Tihulu-Map-Name")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_GET(self):
            if not self._guard():
                return
            path = urlsplit(self.path)
            if path.path in ("/", "/index.html", "/install.html", "/app.js", "/style.css", "/manifest.webmanifest", "/icon.svg", "/sw.js", "/multi_sources.js", "/receiver_coverage.js", "/rf_history_models.js", "/rf_history_worker.js", "/rf_history_client.js", "/rf_history_ui.js", "/map_motion.js", "/rf_timing_lab.js", "/flight_location_ui.mjs", "/location_search.mjs", "/cities-de-tr.json", "/CITY_DATA_LICENSE.md", "/browser_usb.mjs", "/adsb_worker.mjs", "/usb_tools.mjs"):
                name = "index.html" if path.path == "/" else path.path[1:]
                file = STATIC_DIR / name
                if not file.is_file():
                    self._send(HTTPStatus.NOT_FOUND, {"error": "Web asset missing."})
                    return
                raw = file.read_bytes()
                mime = ("text/html" if name.endswith(".html") else
                        "application/javascript" if name.endswith((".js", ".mjs")) else
                        "text/css" if name.endswith(".css") else
                        "application/json" if name.endswith(".json") else
                        "text/markdown" if name.endswith(".md") else
                        "application/manifest+json" if name.endswith(".webmanifest") else
                        "image/svg+xml")
                self._headers(HTTPStatus.OK, mime + "; charset=utf-8", len(raw))
                self.wfile.write(raw)
                return
            if path.path == "/offline-map/status":
                archives = discover()
                active = select_offline_map(bridge.offline_map_name)
                bridge.offline_map_path = active[0] if active else None
                self._send(HTTPStatus.OK, {
                    "available": bool(archives),
                    "active": active[1]["name"] if active else None,
                    "archives": [m for _, m in archives],
                    "directory": str(MAP_ROOT),
                    "format": "raster MBTiles (PNG/JPEG/WebP)",
                    "note": "Use licensed offline map packages. No OSM tile bulk downloads."})
                return
            if path.path.startswith("/offline-tiles/"):
                match = re.fullmatch(r"/offline-tiles/(\d{1,2})/(\d{1,8})/(\d{1,8})\.png", path.path)
                # Do not rescan every directory and open every MBTiles
                # metadata table on each individual map tile request.
                selected = bridge.offline_map_path
                if selected is None or not selected.is_file():
                    active = select_offline_map(bridge.offline_map_name)
                    selected = active[0] if active else None
                    bridge.offline_map_path = selected
                if not match or selected is None:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "Offline map unavailable."})
                    return
                tile = read_tile(selected, *(int(x) for x in match.groups()))
                if not tile:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "No offline tile in this archive."})
                    return
                raw,mime = tile
                self._headers(HTTPStatus.OK, mime, len(raw))
                self.wfile.write(raw)
                return
            if path.path == "/tar1090":
                self.send_response(HTTPStatus.PERMANENT_REDIRECT)
                self.send_header("Location", "/tar1090/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path.path.startswith("/tar1090/"):
                asset = tar_asset_path(path.path)
                if asset is None:
                    self._send(HTTPStatus.NOT_FOUND, {
                        "error": "Local tar1090 static assets are not installed. "
                                 "Open the Internet-enabled hosted tar1090 or "
                                 "run the Pop!_OS installer to cache the frontend."})
                    return
                raw = asset.read_bytes()
                mime = mimetypes.guess_type(str(asset))[0] or "application/octet-stream"
                # GIS/aircraft static databases can be big but are never remote
                # proxy endpoints. Browser cache is safe for these read-only assets.
                self._headers(HTTPStatus.OK, mime, len(raw))
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
            if path.path == "/api/tar-status":
                self._send(HTTPStatus.OK, bridge.tar1090_status())
                return
            if path.path == "/api/search-location":
                self._send(HTTPStatus.OK, {"place": bridge.get_saved_search_place()})
                return
            if path.path == "/api/rf-history/status":
                self._send(HTTPStatus.OK, bridge.rf_history.status())
                return
            if path.path == "/api/rf-history/records":
                try:
                    query = parse_qs(path.query)
                    sid = int(query.get("session", ["0"])[0])
                    after = int(query.get("after", ["0"])[0])
                    limit = int(query.get("limit", ["5000"])[0])
                    self._send(HTTPStatus.OK, bridge.rf_history.page(sid, after, limit))
                except (ValueError, OverflowError) as exc:
                    self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
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
                networks = (parse_provider_selection(one("net", ""))
                            if "net" in query else None)
                self._send(HTTPStatus.OK, bridge.snapshot(mode, lat, lon, radius, networks))
            except (DataError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def do_POST(self):
            if not self._guard():
                return
            endpoint = urlsplit(self.path).path
            if endpoint not in ("/api/control", "/api/search-location",
                                "/api/offline-map/select", "/api/offline-map/import",
                                "/api/rf-history/config"):
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "Pairing token required."})
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if endpoint == "/api/offline-map/import":
                    # Explicit user-chosen raster MBTiles file. Stream to a
                    # private temporary file instead of buffering gigabytes.
                    name = unquote(self.headers.get("X-Tihulu-Map-Name", ""))
                    if (not SAFE_NAME.fullmatch(name) or
                            not 0 < n <= MAX_MAP_BYTES or
                            self.headers.get("Content-Type") != "application/octet-stream"):
                        raise DataError("Import a valid raster .mbtiles archive (maximum 1 GiB).")
                    MAP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
                    fd,temp_name = tempfile.mkstemp(prefix=".import-", suffix=".mbtiles",
                                                   dir=MAP_ROOT)
                    temp = Path(temp_name)
                    try:
                        with os.fdopen(fd, "wb") as output:
                            remaining = n
                            while remaining:
                                chunk = self.rfile.read(min(1_048_576, remaining))
                                if not chunk:
                                    raise DataError("Incomplete map upload.")
                                output.write(chunk)
                                remaining -= len(chunk)
                        info = map_metadata(temp)
                        if not info:
                            raise DataError("Only raster MBTiles with valid tile data schema and PNG/JPEG/WebP format are supported.")
                        dest = MAP_ROOT / name
                        if dest.exists():
                            raise DataError("A map with this filename already exists; rename the imported file.")
                        temp.replace(dest)
                        bridge.offline_map_name = name
                        bridge.offline_map_path = dest
                        self._send(HTTPStatus.OK, {"imported": name, "map": info})
                        return
                    finally:
                        temp.unlink(missing_ok=True)
                if not 1 <= n <= MAX_BODY:
                    raise DataError("Invalid request length.")
                body = json.loads(self.rfile.read(n))
                if endpoint == "/api/offline-map/select":
                    name = body.get("name") if isinstance(body, dict) else None
                    active = select_offline_map(name)
                    if name is not None and (not isinstance(name, str) or not active):
                        raise DataError("Offline map archive not found.")
                    bridge.offline_map_name = name
                    bridge.offline_map_path = active[0] if active else None
                    self._send(HTTPStatus.OK, {"active": active[1]["name"] if active else None})
                    return
                if endpoint == "/api/rf-history/config":
                    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
                        raise DataError("Invalid History action.")
                    self._send(HTTPStatus.OK, bridge.rf_history.config(body["action"]))
                    return
                if endpoint == "/api/search-location":
                    self._send(HTTPStatus.OK, {"place": bridge.save_search_place(body)})
                    return
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
