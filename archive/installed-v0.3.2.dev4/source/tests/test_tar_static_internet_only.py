"""Full original tar1090 is available on the native loopback bridge without RF.

The static browser frontend must not require readsb, authentication to public
assets, or permission to own a local SDR. Pairing remains mandatory for API.
"""
from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import tihulu_flight_radar.bridge as module


def plane(hex_id="3c1234"):
    return {"hex": hex_id, "lat": 50.93, "lon": 6.96, "seen": 1, "seen_pos": 1}


def test_tar_asset_path_only_allows_existing_files_under_explicit_root(tmp_path):
    root = tmp_path / "tar1090"
    root.mkdir()
    (root / "index.html").write_text("<title>Upstream tar1090</title>")
    (root / "script.js").write_text("window.testTar=true")
    outside = tmp_path / "secret.txt"
    outside.write_text("private")
    (root / "escape").symlink_to(outside)
    assert module.tar_asset_path("/tar1090/", (root,)) == root / "index.html"
    assert module.tar_asset_path("/tar1090/script.js", (root,)) == root / "script.js"
    for value in ("/tar1090/../secret.txt", "/tar1090/%2e%2e/secret.txt",
                  "/tar1090/escape", "/tar1090/%2fetc%2fpasswd",
                  "/api/aircraft", "/tar1090/missing.js", "/tar1090/../../x"):
        assert module.tar_asset_path(value, (root,)) is None, value


def test_native_static_tar1090_and_internet_mode_without_radio(monkeypatch, tmp_path):
    root = tmp_path / "tar1090"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>tar1090</title>")
    (root / "tihulu-browser-bridge.js").write_text("window.realTar=true")
    monkeypatch.setattr(module, "TAR_CACHE_DIR", root)
    bridge = module.Bridge(token="test-token")
    bridge.receiver.snapshot = lambda: pytest.fail("Internet-only must not read RF")
    bridge.multi_online.fetch = lambda lat, lon, radius, networks: (
        [plane()], {"provider": "adsb.lol", "error": None,
                    "state": "available", "providers": {"adsblol": {"count": 1}}}
    )
    srv = ThreadingHTTPServer(("127.0.0.1", 0), module.make_handler(bridge, 0))
    srv.RequestHandlerClass = module.make_handler(bridge, srv.server_port)
    worker = threading.Thread(target=srv.serve_forever, daemon=True)
    worker.start()
    def get(path, token=False):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
        headers = {"Authorization": "Bearer test-token"} if token else {}
        conn.request("GET", path, headers=headers)
        result = conn.getresponse()
        status,body = result.status,result.read()
        conn.close()
        return status,body
    try:
        status,raw = get("/tar1090/index.html")
        assert status == 200
        assert b"<title>tar1090</title>" in raw
        status,raw = get("/tar1090/tihulu-browser-bridge.js")
        assert status == 200
        status,raw = get("/api/aircraft?mode=internet&lat=50.93&lon=6.96&radius=100&net=adsblol")
        assert status == 401, "Static resources are public; real API requires pairing"
        status,raw = get("/api/aircraft?mode=internet&lat=50.93&lon=6.96&radius=100&net=adsblol",token=True)
        assert status == 200
        value = json.loads(raw)
        assert value["counts"] == {"antenna": 0, "internet": 1, "combined": 1}
        assert value["aircraft"][0]["sources"] == ["internet"]
        assert value["sources"]["antenna"]["state"] == "disabled"
    finally:
        srv.shutdown()
        srv.server_close()
        worker.join(timeout=2)


def test_linux_installer_stages_real_static_tar_without_touching_readsb():
    script = Path(__file__).resolve().parents[1].joinpath("scripts/install-linux.sh").read_text()
    assert "git clone -q --depth 1 --single-branch --branch gh-pages" in script
    assert "sparse-checkout set tar1090" in script
    assert "tihulu-browser-bridge.js" in script
    assert "rm -rf \"$stage\"" in script
    assert "pipx install --force" in script
    assert "sudo systemctl start readsb" not in script
    assert "sudo systemctl stop readsb" not in script
