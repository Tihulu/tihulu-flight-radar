"""Multiple optional Internet aircraft providers must never change RF provenance."""
import json
import time
from io import BytesIO

import pytest

from tihulu_flight_radar.bridge import Bridge
from tihulu_flight_radar.network_sources import (
    MultiNetworkProvider, normalize_provider, parse_provider_selection,
)
from tihulu_flight_radar.core import DataError


def _plane(hex_id, lat=50.95, lon=6.97):
    return {"hex": hex_id, "lat": lat, "lon": lon,
            "seen": 2, "seen_pos": 3, "flight": "TEST123"}


def test_normalize_adsbfi_milliseconds_and_opensky_units():
    now = time.time()
    rows, _ = normalize_provider(
        "adsbfi", {"now": now * 1000, "ac": [_plane("3c1234")]},
        50.938, 6.96, 100, now=now)
    assert len(rows) == 1
    vector = ["3c1234", "TEST", "Germany", now - 3, now - 1,
              6.97, 50.95, 10000, False, 220, 170, 1,
              None, 10000, "7000", False, 0]
    result, _ = normalize_provider(
        "opensky", {"time": now, "states": [vector]},
        50.938, 6.96, 100, now=now)
    assert len(result) == 1
    assert abs(result[0]["alt_baro"] - 32808) < 2
    assert abs(result[0]["gs"] - 427.65) < 1
    with pytest.raises(DataError):
        normalize_provider("adsbfi", {"now": (now - 200)*1000, "ac":[]},
                           50.938, 6.96, 100, now=now)


def test_provider_selection_allows_only_pinned_known_hosts():
    assert parse_provider_selection("adsbfi,adsblol,adsbfi") == ("adsblol", "adsbfi")
    with pytest.raises(DataError):
        parse_provider_selection("https://internal.example")
    with pytest.raises(DataError):
        parse_provider_selection("airplaneslive")
    with pytest.raises(DataError):
        parse_provider_selection("")


def test_native_collector_merges_networks_and_retains_raw_provenance(monkeypatch):
    import tihulu_flight_radar.network_sources as ns

    now = time.time()
    requested = []

    class Response(BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    class Opener:
        def open(self, request, timeout):
            url = request.full_url
            requested.append(url)
            if "adsb.fi" in url:
                payload = {"now": now*1000, "ac": [_plane("3C1234"), _plane("abcdef")]}
            elif "adsb.lol" in url:
                payload = {"now": now, "ac": [_plane("3c1234")]}
            else:
                raise AssertionError("Unexpected provider")
            return Response(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(ns, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(ns, "ProxyHandler", lambda *_: object())
    provider = MultiNetworkProvider()
    rows, status = provider.fetch(50.938, 6.96, 100, ("adsblol", "adsbfi"))
    assert len(rows) == 2
    overlap = next(x for x in rows if x["hex"] == "3c1234")
    assert overlap["internet_providers"] == ["adsblol", "adsbfi"]
    assert set(overlap["observations"]["internet_sources"]) == {"adsblol", "adsbfi"}
    assert status["providers"]["adsblol"]["count"] == 1
    assert status["providers"]["adsbfi"]["count"] == 2
    assert len(requested) == 2
    again, _ = provider.fetch(50.938, 6.96, 100, ("adsblol", "adsbfi"))
    assert len(again) == 2
    assert len(requested) == 2, "Cache should prevent 15-second duplicate requests"
    chosen, _ = provider.fetch(50.938, 6.96, 100, ("adsblol",))
    assert len(chosen) == 1, "Layer off removes unselected provider-only planes"


def test_bridge_maintains_rf_priority_and_i_r_badges():
    bridge = Bridge(token="test")
    bridge.receiver.snapshot = lambda: {
        "aircraft": [_plane("3c1234")], "messages": 8}
    bridge.online.fetch = lambda *_: (_ for _ in ()).throw(
        AssertionError("Legacy online path used"))
    bridge.multi_online.fetch = lambda *_: (
        [_plane("3c1234") | {
            "internet_providers": ["adsblol", "adsbfi"],
            "observations": {"internet_sources": {"adsblol": _plane("3c1234"),
                                                   "adsbfi": _plane("3c1234")}}}],
        {"provider": "adsb.lol + adsb.fi", "state": "available", "error": None,
         "providers": {"adsblol": {"count": 1}, "adsbfi": {"count": 1}}})
    result = bridge.snapshot("hybrid", 50.938, 6.96, 100,
                             networks=("adsblol", "adsbfi"))
    assert result["counts"] == {"antenna": 1, "internet": 1, "combined": 1}
    assert result["aircraft"][0]["sources"] == ["antenna", "internet"]
    assert result["aircraft"][0]["position_source"] == "antenna"
    assert result["aircraft"][0]["internet_providers"] == ["adsblol", "adsbfi"]
    assert result["sources"]["antenna"]["messages"] == 8
