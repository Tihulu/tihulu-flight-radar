"""Tar1090 launch focus without overwriting upstream tar1090 settings.

Official tar1090 query parameters documented at:
https://github.com/wiedehopf/tar1090/blob/master/README-query.md
This module does not mutate tar1090 files, services, GPS positions or data.
"""
from __future__ import annotations

import math
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .core import position_is_fresh, recently_seen

GERMANY = (51.1657, 10.4515)


def _coordinates(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    lat, lon = value
    if (any(isinstance(x, bool) or not isinstance(x, (float, int))
            or not math.isfinite(x) for x in (lat, lon))
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        return None
    return float(lat), float(lon)


def _distance_sq(a: dict, origin: tuple[float, float]) -> float:
    # Sufficient only for candidate selection, not for distance claims.
    dy = a["lat"] - origin[0]
    dx = (a["lon"] - origin[1]) * math.cos(math.radians(origin[0]))
    return dx * dx + dy * dy


def choose_tar_focus(snapshot: dict | None, receiver: tuple | None = None):
    """Return observed local target, authorized reference or Germany viewport."""
    anchor = _coordinates(receiver) or GERMANY
    aircraft = (snapshot or {}).get("aircraft", [])
    eligible = [a for a in aircraft
                if isinstance(a, dict) and recently_seen(a) and position_is_fresh(a)]
    if eligible:
        chosen = min(eligible, key=lambda a: _distance_sq(a, anchor))
        hexid = chosen.get("hex")
        icao = (hexid.lower() if isinstance(hexid, str)
                and len(hexid) == 6
                and all(c in "0123456789abcdefABCDEF" for c in hexid) else None)
        return {"lat": chosen["lat"], "lon": chosen["lon"], "zoom": 10,
                "icao": icao, "focus": "local-aircraft"}
    if _coordinates(receiver):
        return {"lat": anchor[0], "lon": anchor[1], "zoom": 10,
                "icao": None, "focus": "authorized-receiver"}
    return {"lat": GERMANY[0], "lon": GERMANY[1], "zoom": 7,
            "icao": None, "focus": "germany-default"}


def focused_tar_url(base: str, snapshot: dict | None = None,
                    receiver: tuple | None = None) -> str:
    """Build tar1090 official URL params. Never rely on cached USA viewport."""
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Valid tar1090 HTTP(S) URL required.")
    focus = choose_tar_focus(snapshot, receiver)
    # Respect other existing URL options, but replace only camera parameters.
    pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in (
                 "icao", "zoom", "sitelat", "sitelon", "centerreceiver", "noisolation")]
    pairs.extend([("SiteLat", f"{focus['lat']:.6f}"),
                  ("SiteLon", f"{focus['lon']:.6f}"),
                  ("centerReceiver", ""), ("zoom", str(focus["zoom"]))])
    if focus["icao"]:
        pairs.extend([("icao", focus["icao"]), ("noIsolation", "")])
    query = urlencode(pairs)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
