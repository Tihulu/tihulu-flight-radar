"""Tar1090 focus and independent SDR cleanup regression."""
from urllib.parse import parse_qs, urlsplit

import pytest

from tihulu_flight_radar import control
from tihulu_flight_radar.core import DataError
from tihulu_flight_radar.tar_map import COLOGNE, focused_tar_url


def aircraft(code="3c1234", lat=50.9, lon=7.1, seen=1, seen_pos=1):
    return dict(hex=code, lat=lat, lon=lon, seen=seen, seen_pos=seen_pos)


def params(url):
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_tar_camera_selects_nearest_genuine_local_aircraft_and_preserves_other_planes():
    data={"aircraft":[aircraft("aabbcc", 41.5, -74.0), aircraft("3c1234", 50.9, 7.1)]}
    q=params(focused_tar_url("http://127.0.0.1/tar1090/?enableLabels", data))
    assert q["icao"] == ["3c1234"]
    assert "noIsolation" in q
    assert q["tihuluFocusLat"] == ["50.900000"]
    assert "SiteLat" not in q
    assert q["rangeRings"] == ["0"]
    assert q["tihuluFocusLon"] == ["7.100000"]
    assert "SiteLon" not in q
    assert "centerReceiver" not in q
    assert q["zoom"] == ["10"]
    assert "enableLabels" in q


def test_tar_camera_ignores_stale_positions_and_uses_germany_default():
    data={"aircraft":[aircraft(seen=180), aircraft(seen_pos=150)]}
    q=params(focused_tar_url("http://localhost/tar1090/?SiteLat=39&SiteLon=-99&zoom=4",data))
    assert q["tihuluFocusLat"] == [f"{COLOGNE[0]:.6f}"]
    assert "SiteLat" not in q
    assert q["tihuluFocusLon"] == [f"{COLOGNE[1]:.6f}"]
    assert "SiteLon" not in q
    assert q["zoom"] == ["9"]
    assert "icao" not in q


def test_tar_camera_authorized_receiver_precedes_germany_only_if_no_aircraft():
    q=params(focused_tar_url("http://127.0.0.1/tar1090/", {"aircraft":[]},
                             receiver=(38.4, 27.1)))
    assert q["tihuluFocusLat"] == ["38.400000"]
    assert q["tihuluFocusLon"] == ["27.100000"]


def test_receiver_close_releases_preexisting_linux_readsb_when_requested(monkeypatch):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda name: (True, "active"))
    called=[]
    monkeypatch.setattr(control,"service_action",lambda action: called.append(action) or "stopped")
    receiver=control.ReceiverController()
    receiver.close(release_local_service=True)
    assert called == ["stop"]


def test_receiver_close_does_not_stop_unowned_services_without_explicit_release(monkeypatch):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda name: (True, "active"))
    called=[]
    monkeypatch.setattr(control,"service_action",lambda action: called.append(action) or "stopped")
    receiver=control.ReceiverController()
    receiver.close()
    assert not called


def test_receiver_close_does_not_control_remote_receiver(monkeypatch):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "service_action", lambda action: pytest.fail("remote was stopped"))
    receiver=control.ReceiverController()
    receiver.configure("Remote JSON", "http://receiver.lan/data/aircraft.json")
    receiver.close(release_local_service=True)


def test_failed_sdr_release_is_not_silently_reported_as_success(monkeypatch):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda name: (True, "active"))
    def fail(_action): raise DataError("insufficient service permission")
    monkeypatch.setattr(control,"service_action",fail)
    receiver=control.ReceiverController()
    with pytest.raises(DataError,match="insufficient"):
        receiver.close(release_local_service=True)

def test_authorized_location_has_priority_over_nearest_radio_plane():
    data={"aircraft":[aircraft("3c1234", 50.9, 7.1)]}
    q=params(focused_tar_url("http://localhost/tar1090/", data,
                             receiver=(39.9, 32.9)))
    assert q["tihuluFocusLat"] == ["39.900000"]
    assert q["tihuluFocusLon"] == ["32.900000"]
    assert "icao" not in q
