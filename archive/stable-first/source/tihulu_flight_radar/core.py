"""Safe ADS-B JSON input, derived statistics, and export.

No simulated aircraft are produced. Aircraft without a valid, fresh position
are counted but must not be drawn as positioned aircraft.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_JSON_BYTES = 4 * 1024 * 1024
FRESH_SECONDS = 60
DATA_TIMEOUT_SECONDS = 15


class DataError(RuntimeError):
    pass


def position_is_fresh(aircraft: dict) -> bool:
    lat, lon = aircraft.get("lat"), aircraft.get("lon")
    age = aircraft.get("seen_pos")
    return (
        all(isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) for v in (lat, lon, age))
        and -90 <= lat <= 90 and -180 <= lon <= 180
        and 0 <= age <= FRESH_SECONDS
    )


def recently_seen(aircraft: dict) -> bool:
    age = aircraft.get("seen")
    return (isinstance(age, (int, float)) and not isinstance(age, bool)
            and math.isfinite(age) and 0 <= age <= FRESH_SECONDS)


def validate_snapshot(data: object, received_at: float | None = None) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("aircraft"), list):
        raise DataError("Invalid aircraft.json payload.")
    now = data.get("now")
    if isinstance(now, (int, float)) and not isinstance(now, bool):
        if not math.isfinite(now) or abs((received_at or time.time()) - now) > DATA_TIMEOUT_SECONDS:
            raise DataError("Receiver data is stale (timestamp exceeds 15 seconds).")
    if len(data["aircraft"]) > 100000:
        raise DataError("Aircraft list is unexpectedly large.")
    return data


def summarize(data: dict) -> dict:
    aircraft = [a for a in data.get("aircraft", [])
                if isinstance(a, dict) and recently_seen(a)]
    positions = [a for a in aircraft if position_is_fresh(a)]
    signals = [a["rssi"] for a in aircraft
               if isinstance(a.get("rssi"), (int, float))
               and not isinstance(a["rssi"], bool) and math.isfinite(a["rssi"])]
    total = data.get("messages", 0)
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        total = 0
    return {
        "aircraft": len(aircraft),
        "positioned": len(positions),
        "messages": total,
        "mean_rssi": round(sum(signals) / len(signals), 1) if signals else None,
    }


def visible_aircraft(data: dict) -> list[dict]:
    """Retain actual received fields, but never invent a missing position."""
    return [a for a in data.get("aircraft", [])
            if isinstance(a, dict) and recently_seen(a)]


def read_local(path: Path) -> dict:
    try:
        if not path.is_file():
            raise DataError("Receiver data file not found.")
        if time.time() - path.stat().st_mtime > DATA_TIMEOUT_SECONDS:
            raise DataError("Receiver data file has not updated recently.")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise DataError("Receiver data file is too large.")
        return validate_snapshot(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, UnicodeError) as exc:
        raise DataError(f"Cannot read local receiver data: {exc}") from exc


def validate_remote_url(url: str) -> str:
    url = url.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise DataError("Enter a full http:// or https:// aircraft.json URL.")
    if parsed.username or parsed.password or parsed.fragment:
        raise DataError("Credentials and fragments are not allowed in receiver URLs.")
    return url


def read_remote(url: str) -> dict:
    url = validate_remote_url(url)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "TihuluFlightRadar/0.3"})
    try:
        with urlopen(request, timeout=4) as response:
            length = response.read(MAX_JSON_BYTES + 1)
        if len(length) > MAX_JSON_BYTES:
            raise DataError("Remote receiver JSON exceeds size limit.")
        return validate_snapshot(json.loads(length.decode("utf-8")))
    except DataError:
        raise
    except (OSError, ValueError, UnicodeError) as exc:
        raise DataError(f"Cannot reach remote receiver: {exc}") from exc


# Kept from the original GTK dashboard: optional local tar1090 URL discovery
# and read-only SDR conflict information. Neither helper changes the receiver.
TAR1090_URLS = (
    "http://127.0.0.1/tar1090/",
    "http://127.0.0.1:8504/",
    "http://127.0.0.1:8504/tar1090/",
)
CONFLICT_PROCESSES = frozenset({
    "gqrx", "welle-io", "welle.io", "rtl_test", "rtl_433",
    "rtl_fm", "rtl_tcp", "rtl_adsb", "sdrpp", "sdr++", "cubicsdr",
})


def detect_sdr_processes() -> list[str]:
    """Advisory check only; do not terminate competing SDR processes."""
    import subprocess

    try:
        result = subprocess.run(
            ["ps", "-eo", "comm="], capture_output=True, text=True,
            timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted({name.strip() for name in result.stdout.splitlines()
                   if name.strip().lower() in CONFLICT_PROCESSES})


def tar1090_data_fresh(payload: object, *, now: float | None = None) -> bool:
    """A served tar1090 HTML page does not prove readsb data exists.

    /tar1090/data/aircraft.json must be actual recent decoder JSON. Empty
    lists are allowed; fabricated planes and fixed fake timestamps are not.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("aircraft"), list):
        return False
    observed = payload.get("now")
    current = time.time() if now is None else now
    return (isinstance(observed, (int, float)) and not isinstance(observed, bool)
            and math.isfinite(observed) and 0 <= current - observed <= DATA_TIMEOUT_SECONDS)


def find_tar1090_url() -> str | None:
    """Find a local tar1090 UI backed by actual fresh readsb aircraft.json.

    If browser WebUSB owns the only SDR, readsb is commonly stopped. In
    that case the static tar1090 HTML might still be HTTP 200, but its
    backend is dead: return None instead of showing the misleading grey map.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import ProxyHandler, build_opener
    from urllib.parse import urljoin

    opener = build_opener(ProxyHandler({}))
    for url in TAR1090_URLS:
        try:
            with opener.open(url, timeout=1.6) as response:
                if not (response.status == 200 and
                        "text/html" in response.headers.get("Content-Type", "")):
                    continue
            with opener.open(urljoin(url, "data/aircraft.json"), timeout=1.6) as response:
                if response.status != 200:
                    continue
                raw = response.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                continue
            payload = json.loads(raw)
            if tar1090_data_fresh(payload):
                return url
        except (URLError, HTTPError, OSError, TimeoutError,
                ValueError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None

def lan_ip() -> str | None:
    """Find the LAN IP for the legacy local tar1090 route."""
    import subprocess

    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True,
            timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    addresses = [ip for ip in result.stdout.split()
                 if ip.count(".") == 3 and not ip.startswith("127.")]
    preferred = [ip for ip in addresses if ip.startswith("192.168.")]
    return (preferred or addresses or [None])[0]


def export_json(data: dict, destination: Path) -> None:
    validate_snapshot(data)
    # Explicit export; do not change or add aircraft measurements.
    destination.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
