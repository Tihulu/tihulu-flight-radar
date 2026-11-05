import pytest

from tihulu_flight_radar.control import ReceiverController, service_action
from tihulu_flight_radar.core import DataError


def test_default_mode_is_valid():
    r = ReceiverController()
    assert r.mode in ("Linux services", "Direct readsb")


def test_cannot_inject_commands():
    with pytest.raises(DataError):
        service_action("start; echo hacked")


def test_remote_mode_never_manages_services():
    r = ReceiverController()
    r.configure("Remote JSON", "http://127.0.0.1/data/aircraft.json")
    with pytest.raises(DataError):
        r.start()
    with pytest.raises(DataError):
        r.stop()
