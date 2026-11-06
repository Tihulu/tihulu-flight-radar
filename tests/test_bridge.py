"""GitHub Pages/local bridge contract: no invented positions, no open controls."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tihulu_flight_radar.bridge import Bridge, _coord, make_handler, merge_aircraft
from tihulu_flight_radar.core import DataError


def aircraft(hex: str, seen=1.0, position=True, **extra):
    a = {"hex": hex, "flight": "REAL123", "seen": seen}
    if position:
        a.update(lat=50.1, lon=7.1, seen_pos=seen)
    a.update(extra)
    return a


def test_duplicate_icao_keeps_independent_raw_observations():
    local = aircraft("3C1234", flight="LOCAL", rssi=-14)
    web = aircraft("3c1234", flight="ONLINE", alt_baro=18000)
    merged = merge_aircraft([local], [web])
    assert len(merged) == 1
    assert merged[0]["flight"] == "LOCAL"
    assert merged[0]["sources"] == ["antenna", "internet"]
    assert merged[0]["position_source"] == "antenna"
    assert merged[0]["observations"]["internet"]["alt_baro"] == 18000
    assert merged[0]["observations"]["antenna"]["rssi"] == -14


def test_local_missing_position_may_show_online_position_with_provenance():
    a = merge_aircraft([aircraft("aaaaab", position=False)],
                       [aircraft("AAAAAB", lat=52.2, lon=13.4)])[0]
    assert (a["lat"], a["lon"]) == (52.2, 13.4)
    assert a["position_source"] == "internet"


def test_non_icao_and_stale_items_never_merge_or_create_positions():
    result = merge_aircraft(
        [aircraft("~12345", position=False), aircraft("abcdef", seen=120)],
        [aircraft("~12345", position=False)])
    assert len(result) == 2
    assert not any("lat" in row for row in result)
    assert result[0]["position_source"] is None


@pytest.mark.parametrize("value", ["NaN", "Infinity", "999", "not-a-number"])
def test_coordinates_reject_nonfinite_and_outside_bounds(value):
    with pytest.raises(DataError):
        _coord(value, 0, -90, 90)


def test_internet_only_has_no_local_device_calls():
    bridge = Bridge(token="test")
    bridge.receiver.snapshot = lambda: (_ for _ in ()).throw(AssertionError("USB used"))
    bridge.online.fetch = lambda *args: ([aircraft("123456")], {"provider": "test", "error": None})
    result = bridge.snapshot("internet", 51.1, 10.4, 100)
    assert result["counts"] == {"antenna": 0, "internet": 1, "combined": 1}
    assert result["active_sources"] == ["internet"]


def test_auto_prefers_existing_receiver_data_without_online_poll():
    bridge = Bridge(token="test")
    bridge.receiver.snapshot = lambda: {"aircraft": [aircraft("123456")], "messages": 456}
    bridge.online.fetch = lambda *args: (_ for _ in ()).throw(AssertionError("Internet used"))
    result = bridge.snapshot("auto", 51.1, 10.4, 100)
    assert result["counts"]["antenna"] == 1
    assert result["sources"]["antenna"]["messages"] == 456


def test_hybrid_merges_and_distinguishes_counts():
    bridge = Bridge(token="test")
    bridge.receiver.snapshot = lambda: {"aircraft": [aircraft("123456")], "messages": 123}
    bridge.online.fetch = lambda *args: (
        [aircraft("123456"), aircraft("ABCDEF")], {"provider": "test", "error": None})
    result = bridge.snapshot("hybrid", 50.0, 8.0, 100)
    assert result["counts"] == {"antenna": 1, "internet": 2, "combined": 2}


def test_hardware_control_opt_in():
    bridge = Bridge(token="test")
    with pytest.raises(DataError, match="disabled"):
        bridge.control("start")


def test_http_pairing_host_origin_cors_and_static_assets():
    bridge = Bridge(token="secret-for-test")
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    server.RequestHandlerClass = make_handler(bridge, server.server_port)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base+"/index.html", timeout=3) as r:
            assert b"TIHULU FLIGHT RADAR" in r.read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base+"/api/status", timeout=3)
        assert e.value.code == 401
        req = urllib.request.Request(base+"/api/status", headers={
            "Authorization":"Bearer secret-for-test",
            "Origin":"https://tihulu.github.io"
        })
        with urllib.request.urlopen(req, timeout=3) as r:
            assert r.headers["Access-Control-Allow-Origin"] == "https://tihulu.github.io"
            assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
            assert "control_enabled" in json.loads(r.read())
        req = urllib.request.Request(base+"/api/status", headers={
            "Authorization":"Bearer secret-for-test",
            "Origin":"https://evil.example"
        })
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=3)
        assert e.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_internet_provider_falls_back_after_primary_429_without_fabricated_aircraft(monkeypatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError
    import tihulu_flight_radar.bridge as module

    calls = []
    class FakeResponse:
        def __init__(self, body):
            self.body = body
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self, _count):
            return self.body
    class FakeOpener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            if "api.adsb.lol" in request.full_url:
                h=Message()
                h["Retry-After"]="90"
                raise HTTPError(request.full_url, 429, "Slow down", h, None)
            return FakeResponse(json.dumps({
                "ac":[aircraft("3c1234",seen=2.0,position=True)]
            }).encode("utf-8"))
    monkeypatch.setattr(module, "build_opener", lambda *_: FakeOpener())
    monkeypatch.setattr(module, "ProxyHandler", lambda *_: object())
    provider=module.DataProvider()
    result,status=provider.fetch(50.9,7.1,100)
    assert len(result)==1
    assert result[0]["hex"]=="3c1234"
    assert status["provider"]=="adsb.fi"
    assert "personal/non-commercial" in status["attribution"]
    assert len(calls)==2
    result2,status2=provider.fetch(50.9,7.1,100)
    assert status2["cached"] is True
    assert len(calls)==2


def test_internet_provider_all_feeds_down_exposes_errors_not_fake_positions(monkeypatch):
    from urllib.error import URLError
    import tihulu_flight_radar.bridge as module
    class Offline:
        def open(self, request, timeout):
            raise URLError("network disconnected")
    monkeypatch.setattr(module, "build_opener", lambda *_: Offline())
    monkeypatch.setattr(module, "ProxyHandler", lambda *_: object())
    provider=module.DataProvider()
    result,status=provider.fetch(50.9,7.1,100)
    assert result==[]
    assert "adsb.lol" in status["error"]
    assert "adsb.fi" in status["error"]
    assert status["updated_at"] is None
