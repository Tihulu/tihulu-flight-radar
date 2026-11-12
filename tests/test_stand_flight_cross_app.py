"""STAND-FLIGHT: two independent TIHULU app sessions with inert fakes.

Test-only regression contract. No real readsb, systemctl, sudo, USB,
network provider, external app, installation, local socket or process launch.

The foreign-service Quit assertion intentionally exposes the current main
owner-provenance defect; it is NOT a waiver or a green hardware result.
"""
from __future__ import annotations

from tihulu_flight_radar import bridge as bridge_module
from tihulu_flight_radar import control
from tihulu_flight_radar import map_server


def test_internet_only_flight_quit_preserves_other_tihulu_app_service_pair(monkeypatch):
    """A separately running TIHULU app must retain its already-owned receiver.

    Flight only displays fake Internet aircraft and never requested RF. Both
    services were active BEFORE Flight was opened. Quitting Flight with its
    default release preference must not shut down the other application.
    """
    foreign_app = {
        "name": "simulated-independent-TIHULU-app",
        "running": True,
        "services": {"readsb.service": True, "tar1090.service": True},
    }
    calls = []
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        control, "_unit_active",
        lambda unit: (foreign_app["services"][unit],
                      "active" if foreign_app["services"][unit] else "inactive"),
    )

    def service_action(action):
        calls.append(action)
        if action == "stop":
            for unit in foreign_app["services"]:
                foreign_app["services"][unit] = False
        return "fake " + action

    monkeypatch.setattr(control, "service_action", service_action)
    flight = bridge_module.Bridge(token="inert-stand-flight", allow_control=False)
    # Any local receiver access in Internet-only mode is a regression.
    flight.receiver.snapshot = lambda: (_ for _ in ()).throw(
        AssertionError("Internet-only Flight must not poll another app's SDR"))
    flight.online.fetch = lambda lat, lon, radius: (
        [{"hex": "3c1234", "lat": 50.94, "lon": 6.96,
          "seen": 0.4, "seen_pos": 0.4}],
        {"state": "available", "provider": "synthetic", "error": None},
    )
    snapshot = flight.snapshot("internet", 50.94, 6.96, 100)
    assert snapshot["counts"] == {"antenna": 0, "internet": 1, "combined": 1}
    assert snapshot["aircraft"][0]["position_source"] == "internet"
    assert snapshot["sources"]["antenna"]["state"] == "disabled"
    assert foreign_app["running"]

    # This is a mocked source-contract test. It must fail on unsafe main and
    # pass only after a separately reviewed, ownership-aware fix is integrated.
    flight.receiver.close(release_local_service=True)
    assert calls == [], "Flight Quit must never stop the other app's services"
    assert foreign_app["services"] == {
        "readsb.service": True, "tar1090.service": True}
    assert foreign_app["running"]


def test_classic_flight_uses_a_different_mock_port_when_other_app_owns_8505(
        monkeypatch):
    """Two apps can hold independent GUI HTTP endpoints without socket takeover."""
    foreign_app = {"name": "synthetic-TIHULU-app", "port": 8505,
                   "listening": True, "shutdowns": 0}
    calls = []

    class OwnedFakeServer:
        server_port = 59001

        def __init__(self):
            self.closes = 0
            self.stops = 0

        def serve_forever(self):
            # Inert thread: no port is bound and no HTTP request is made.
            return None

        def shutdown(self):
            self.stops += 1

        def server_close(self):
            self.closes += 1

    owned = OwnedFakeServer()

    def fake_listener(address, handler):
        calls.append(address)
        if address == ("127.0.0.1", 8505):
            assert foreign_app["listening"]
            raise OSError("synthetic foreign port is occupied")
        assert address == ("127.0.0.1", 0)
        return owned

    monkeypatch.setattr(map_server, "ThreadingHTTPServer", fake_listener)
    flight = map_server.LocalMapServer(lambda: None)
    assert flight.url == "http://127.0.0.1:59001/"
    flight.start()
    flight.close()
    assert calls == [("127.0.0.1", 8505), ("127.0.0.1", 0)]
    assert owned.stops == 1 and owned.closes == 1
    assert foreign_app == {"name": "synthetic-TIHULU-app",
                           "port": 8505, "listening": True, "shutdowns": 0}
