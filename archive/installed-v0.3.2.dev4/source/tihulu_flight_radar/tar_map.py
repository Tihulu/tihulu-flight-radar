"""Tar1090 launch focus without overwriting upstream tar1090 settings.

Official tar1090 query parameters documented at:
https://github.com/wiedehopf/tar1090/blob/master/README-query.md
This module does not mutate tar1090 files, services, GPS positions or data.
"""
from __future__ import annotations

import math
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .core import position_is_fresh, recently_seen

COLOGNE = (50.938, 6.960)
GERMANY = (51.1657, 10.4515)  # legacy constant for compatibility only


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
    explicit_location = _coordinates(receiver)
    if explicit_location:
        return {"lat": explicit_location[0], "lon": explicit_location[1],
                "zoom": 10, "icao": None, "focus": "authorized-location"}
    anchor = COLOGNE
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
    return {"lat": COLOGNE[0], "lon": COLOGNE[1], "zoom": 9,
            "icao": None, "focus": "cologne-default"}


def focused_tar_url(base: str, snapshot: dict | None = None,
                    receiver: tuple | None = None) -> str:
    """Never forge a tar1090 receiver/site location to set the camera.

    The native Qt viewer separately applies map camera focus through OpenLayers.
    SiteLat/SiteLon are real *receiver-site override* parameters, and setting
    them to Germany falsely draws a receiver dot and range circles there.
    """
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Valid tar1090 HTTP(S) URL required.")
    focus = choose_tar_focus(snapshot, receiver)
    pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in ("icao", "zoom", "sitelat", "sitelon",
                                  "centerreceiver", "lockdotcentered",
                                  "noisolation", "rangerings",
                                  "tihulufocuslat", "tihulufocuslon")]
    # Explicitly hide rings, keep tar1090's *actual* receiver location intact.
    pairs.append(("rangeRings", "0"))
    pairs.append(("zoom", str(focus["zoom"])))
    # The Qt viewer reads the Tihulu fields and sets map camera separately.
    # Upstream tar1090 ignores unrecognized query parameters.
    pairs.append(("tihuluFocusLat", f"{focus['lat']:.6f}"))
    pairs.append(("tihuluFocusLon", f"{focus['lon']:.6f}"))
    if focus["icao"]:
        pairs.extend([("icao", focus["icao"]), ("noIsolation", "")])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       urlencode(pairs), parsed.fragment))
