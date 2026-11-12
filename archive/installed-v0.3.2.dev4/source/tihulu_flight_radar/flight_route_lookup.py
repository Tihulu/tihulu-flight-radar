"""Safe opt-in callsign flightroute lookup. No mass scraping or persistence.

Provider: adsbdb.com, whose route data credits David J Taylor (Edinburgh)
and Jim Mason (Glasgow) and must not be bundled into databases. This bridge
queries a SINGLE selected callsign, retains only a short in-memory cache,
does not provide schedules or timestamps, and keeps pairing tokens local.
"""
from __future__ import annotations

import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

CALLSIGN = re.compile(r"^[A-Z0-9]{3,10}$")
MAX_REPLY = 32_768
TTL = 30 * 60


def validate_callsign(value: object) -> str:
    if not isinstance(value, str) or not CALLSIGN.fullmatch(value):
        raise ValueError("A valid 3–10 character uppercase flight callsign is required.")
    return value


def airport(record: object) -> dict | None:
    if not isinstance(record, dict):
        return None
    codes = (record.get("iata_code"), record.get("icao_code"))
    valid = [v.strip().upper() for v in codes if isinstance(v, str)
             and re.fullmatch(r"[A-Z0-9]{3,4}", v.strip().upper())]
    if not valid:
        return None
    result = {"iata_code": valid[0], "icao_code": valid[-1]}
    for field in ("name", "municipality"):
        value = record.get(field)
        if isinstance(value, str) and 1 <= len(value.strip()) <= 110:
            result[field] = value.strip()
    return result


def normalize_route(data: object, callsign: str) -> dict:
    """Strictly keep matching route airports, never treat times as present."""
    response = data.get("response") if isinstance(data, dict) else None
    route = response.get("flightroute") if isinstance(response, dict) else None
    if not isinstance(route, dict):
        return {"response": {"flightroute": None},
                "source": "adsbdb.com · no matching route"}
    found = [str(route[k]).strip().upper() for k in
             ("callsign", "callsign_icao", "callsign_iata")
             if isinstance(route.get(k), str) and route[k].strip()]
    if found and callsign not in found:
        return {"response": {"flightroute": None},
                "source": "adsbdb.com · callsign mismatch"}
    origin, destination = airport(route.get("origin")), airport(route.get("destination"))
    if not origin and not destination:
        return {"response": {"flightroute": None},
                "source": "adsbdb.com · no matching airport data"}
    return {"response": {"flightroute": {
        "callsign": callsign, "origin": origin, "destination": destination,
        "midpoint": airport(route.get("midpoint")),
    }}, "source": "adsbdb.com · live callsign route lookup, not timetable",
        "route_credit": "David J Taylor (Edinburgh) and Jim Mason (Glasgow)"}


class CallsignRouteLookup:
    def __init__(self, opener=None):
        self.lock = threading.Lock()
        self.cache: dict[str, tuple[float, dict]] = {}
        self._opener = opener

    def query(self, callsign: str) -> dict:
        callsign = validate_callsign(callsign)
        now = time.monotonic()
        with self.lock:
            cached = self.cache.get(callsign)
            if cached and now - cached[0] < TTL:
                return cached[1]
            try:
                opener = self._opener or build_opener(ProxyHandler({}))
                request = Request("https://api.adsbdb.com/v0/callsign/" + callsign,
                    headers={"Accept": "application/json",
                             "User-Agent": "TihuluFlightRadar/0.3 (single-flight lookup)"})
                with opener.open(request, timeout=3.5) as response:
                    data = response.read(MAX_REPLY + 1)
                if len(data) > MAX_REPLY:
                    raise ValueError("Route response too large")
                result = normalize_route(json.loads(data), callsign)
                self.cache[callsign] = (now, result)
                if len(self.cache)>256:
                    for key in list(self.cache)[:64]:
                        self.cache.pop(key, None)
                return result
            except HTTPError as error:
                if error.code == 404:
                    result = {"response": {"flightroute": None},
                        "source": "adsbdb.com · route not found"}
                    self.cache[callsign] = (now, result)
                    return result
                return {"response": {"flightroute": None},
                    "error": "adsbdb.com unavailable: HTTP " + str(error.code)}
            except (URLError, OSError, ValueError, UnicodeError) as error:
                return {"response": {"flightroute": None},
                    "error": "Route lookup unavailable: " + str(error)[:120]}
