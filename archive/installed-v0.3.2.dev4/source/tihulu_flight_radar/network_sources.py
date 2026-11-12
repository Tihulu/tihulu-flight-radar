"""Independent, opt-in public Internet layers for the native/paired radar.

The installed stable v0.3.1 path keeps the original DataProvider fallback.
This module never controls an SDR, uploads RF samples, or invents aircraft.
"""
from __future__ import annotations

import json
import math
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from .core import DataError, recently_seen, position_is_fresh

NETWORK_ORDER = ("adsblol", "adsbfi", "opensky", "intelsky")
NETWORK_INFO = {
    "adsblol": ("adsb.lol", "adsb.lol — ODbL 1.0", 35),
    "adsbfi": ("adsb.fi", "adsb.fi — personal, non-commercial; https://adsb.fi", 35),
    "opensky": ("OpenSky", "OpenSky Network — public API credit limits", 300),
    "intelsky": ("IntelSky", "IntelSky.org — limited military/government", 60),
}
MAX_BYTES = 4_194_304


def parse_provider_selection(text: str) -> tuple[str, ...]:
    """Reject arbitrary network URLs and unsupported providers."""
    if not isinstance(text, str) or len(text) > 80:
        raise DataError("Invalid Internet source selection.")
    names = [name.strip() for name in text.split(",")]
    if not names or any(name not in NETWORK_INFO for name in names):
        raise DataError("Choose valid Internet sources: adsblol, adsbfi, opensky, intelsky.")
    return tuple(id_ for id_ in NETWORK_ORDER if id_ in names)


def _icao(item: dict) -> str | None:
    v = item.get("hex")
    if isinstance(v, str) and len(v) == 6 and all(c in "0123456789abcdefABCDEF" for c in v):
        return v.lower()
    return None


def _dist_nm(lat: float, lon: float, alat: float, alon: float) -> float:
    r = math.pi / 180
    dp, dq = (alat-lat)*r, (alon-lon)*r
    v = math.sin(dp/2)**2 + math.cos(lat*r)*math.cos(alat*r)*math.sin(dq/2)**2
    return 3440.065*2*math.asin(math.sqrt(min(1, max(0, v))))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _url(provider: str, lat: float, lon: float, radius: int) -> str:
    if provider == "adsblol":
        return f"https://api.adsb.lol/v2/point/{lat:.3f}/{lon:.3f}/{radius}"
    if provider == "adsbfi":
        return f"https://opendata.adsb.fi/api/v3/lat/{lat:.3f}/lon/{lon:.3f}/dist/{radius}"
    if provider == "intelsky":
        return "https://intelsky.org/api/"
    if provider == "opensky":
        dlat = radius / 60
        dlon = dlat / max(.15, math.cos(math.radians(lat)))
        bbox = {"lamin": max(-90, lat-dlat), "lamax": min(90, lat+dlat),
                "lomin": max(-180, lon-dlon), "lomax": min(180, lon+dlon)}
        return "https://opensky-network.org/api/states/all?" + urlencode(bbox)
    raise DataError("Unknown Internet provider.")


def normalize_provider(provider: str, payload: object, lat: float, lon: float,
                       radius: int, now: float | None = None) -> tuple[list[dict], float]:
    """Translate provider vectors into ADS-B-compatible, age-verified records."""
    now = time.time() if now is None else now
    if provider not in NETWORK_INFO or not isinstance(payload, dict):
        raise DataError("Unexpected public network response.")
    stamp = payload.get("time" if provider == "opensky" else "now")
    if not _number(stamp):
        raise DataError("Internet snapshot missing timestamp.")
    if stamp > 1e12:
        stamp /= 1000
    if not -10 <= now-stamp <= 120:
        raise DataError("Internet provider timestamp stale or in the future.")
    records = payload.get("states" if provider == "opensky" else "ac")
    if not isinstance(records, list):
        raise DataError("Provider aircraft schema invalid.")
    rows, seen_ids = [], set()
    for raw in records[:10000]:
        if provider == "opensky":
            if not isinstance(raw, list) or len(raw) < 12:
                continue
            icao, callsign = raw[0:2]
            pos_time, last_contact = raw[3], raw[4]
            if not _number(last_contact) or not _number(pos_time):
                continue
            altitude, speed, rate = raw[7], raw[9], raw[11]
            plane = {"hex": icao, "flight": callsign, "lon": raw[5],
                     "lat": raw[6], "seen": now-last_contact, "seen_pos": now-pos_time,
                     "alt_baro": altitude*3.280839895 if _number(altitude) else None,
                     "gs": speed*1.943844492 if _number(speed) else None,
                     "track": raw[10],
                     "baro_rate": rate*196.850394 if _number(rate) else None,
                     "squawk": raw[14] if len(raw) > 14 else None}
        elif isinstance(raw, dict):
            plane = dict(raw)
            if provider == "intelsky":
                plane["seen"] = max(0, now-stamp)
                plane["seen_pos"] = max(0, now-stamp)
                plane["observation_age_unknown"] = True
        else:
            continue
        key = _icao(plane)
        if (key is None or key in seen_ids or not recently_seen(plane)
                or not position_is_fresh(plane)
                or _dist_nm(lat, lon, plane["lat"], plane["lon"]) > radius):
            continue
        seen_ids.add(key)
        plane["hex"] = key
        rows.append(plane)
    return rows, stamp


class MultiNetworkProvider:
    """Selected independent feeds, bounded per-provider caching and backoff."""

    def __init__(self):
        self.lock = threading.Lock()
        self.records: dict[str, dict] = {}
        self.cooldowns: dict[str, float] = {}
        self.next_fetch: dict[str, float] = {}
        self.errors: dict[str, str | None] = {}

    def fetch(self, lat: float, lon: float, radius: int,
              selected: tuple[str, ...]) -> tuple[list[dict], dict]:
        if not selected or any(p not in NETWORK_INFO for p in selected):
            raise DataError("No valid Internet layers enabled.")
        key = (round(lat, 1), round(lon, 1), radius)
        now = time.monotonic()
        with self.lock:
            for provider in selected:
                prev = self.records.get(provider)
                if prev and prev["key"] != key:
                    self.records.pop(provider, None)
                    self.next_fetch[provider] = 0
                if now < self.next_fetch.get(provider, 0) or now < self.cooldowns.get(provider, 0):
                    continue
                self.next_fetch[provider] = now + NETWORK_INFO[provider][2]
                try:
                    # No request for airplanes.live: public API is feeder-restricted.
                    request = Request(_url(provider, lat, lon, radius),
                        headers={"Accept": "application/json",
                                 "User-Agent": "TihuluFlightRadar/0.3.1 (personal aircraft map)"})
                    opener = build_opener(ProxyHandler({}))
                    with opener.open(request, timeout=2) as response:
                        raw = response.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES:
                        raise DataError(provider+": response exceeds 4 MiB.")
                    planes, stamp = normalize_provider(
                        provider, json.loads(raw), lat, lon, radius)
                    self.records[provider] = {
                        "key": key, "rows": planes, "stamp": stamp, "stored": time.time()}
                    self.errors[provider] = None
                except HTTPError as exc:
                    self.errors[provider] = provider+": HTTP "+str(exc.code)
                    if exc.code == 429:
                        header = exc.headers.get("Retry-After", "120")
                        try:
                            retry = int(header)
                        except (ValueError, TypeError):
                            retry = 120
                        self.cooldowns[provider] = now + max(60, min(3600, retry))
                    else:
                        self.cooldowns[provider] = now + 120
                except (URLError, OSError, ValueError, DataError) as exc:
                    self.errors[provider] = provider+": "+str(exc)[:130]
                    self.cooldowns[provider] = now + 60
            by_id: dict[str, dict] = {}
            provider_status = {}
            for provider in NETWORK_ORDER:
                if provider not in selected:
                    continue
                item = self.records.get(provider)
                if item is not None and item["key"] != key:
                    item = None
                elapsed = max(0, time.time()-item["stored"]) if item else float("inf")
                live = []
                for original in item["rows"] if item else []:
                    aircraft = dict(original)
                    for agefield in ("seen", "seen_pos"):
                        aircraft[agefield] = original[agefield] + elapsed
                    if recently_seen(aircraft) and position_is_fresh(aircraft):
                        live.append(aircraft)
                provider_status[provider] = {
                    "state": "available" if item and elapsed <= 60 else "unavailable",
                    "error": self.errors.get(provider),
                    "count": len(live),
                    "updated_at": item["stamp"] if item else None,
                    "attribution": NETWORK_INFO[provider][1]}
                for aircraft in live:
                    hex_id = aircraft["hex"]
                    old = by_id.get(hex_id)
                    if old:
                        old["internet_providers"].append(provider)
                        old["observations"]["internet_sources"][provider] = dict(aircraft)
                        if aircraft["seen_pos"] < old["seen_pos"]:
                            old.update({k: aircraft[k] for k in ("lat", "lon", "seen", "seen_pos")})
                            old["position_provider"] = provider
                    else:
                        row = dict(aircraft)
                        row["internet_providers"] = [provider]
                        row["position_provider"] = provider
                        row["observations"] = {"internet_sources": {provider: dict(aircraft)}}
                        by_id[hex_id] = row
            working = [p for p in selected if provider_status[p]["state"] == "available"]
            last_seen = max([provider_status[p]["updated_at"] or 0 for p in working] or [0])
            error = None if working else " | ".join(
                self.errors.get(p) or p+": not available" for p in selected)
            return list(by_id.values()), {
                "state": "available" if working else "unavailable",
                "provider": " + ".join(NETWORK_INFO[p][0] for p in working) or "Selected networks",
                "attribution": " · ".join(NETWORK_INFO[p][1] for p in selected),
                "updated_at": last_seen or None, "error": error,
                "providers": provider_status}
