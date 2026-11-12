"""Loopback map server contract tests. Sample JSON is test-only, never live traffic."""
import json
from urllib.request import urlopen

from tihulu_flight_radar.map_server import LocalMapServer


def test_loopback_map_opens_without_aircraft():
    server = LocalMapServer(lambda: {"now": 0, "messages": 0, "aircraft": []})
    try:
        assert server.url.startswith("http://127.0.0.1:")
        server.start()
        with urlopen(server.url, timeout=4) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
        assert "Show Germany" in html
        assert "GERMANY_DEFAULT" in html
        with urlopen(server.url + "map_focus.js", timeout=4) as response:
            js = response.read().decode("utf-8")
            assert "chooseFocus" in js
        with urlopen(server.url + "api/aircraft", timeout=4) as response:
            snapshot = json.loads(response.read())
            assert snapshot["aircraft"] == []
    finally:
        server.close()
