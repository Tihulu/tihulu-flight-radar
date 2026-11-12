"""Inert Flight Radar service ownership regression characterization.

All Linux service operations and state checks are mocked. No systemctl, sudo,
readsb/tar1090 process, receiver or network service is invoked by these tests.
The marked XFAIL represents a known P0 gap on canonical main, not an acceptance.
"""
from types import SimpleNamespace

import pytest

import tihulu_flight_radar.control as control
from tihulu_flight_radar.core import DataError


@pytest.fixture
def fake_services(monkeypatch):
    events = []
    active = {"readsb.service": True, "tar1090.service": True}
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active",
                        lambda unit: (active[unit], "active" if active[unit] else "inactive"))
    monkeypatch.setattr(control, "service_action",
                        lambda action: events.append(action) or "fake " + action)
    return events, active


def test_existing_service_exit_opt_out_never_stops_external(fake_services):
    events, _ = fake_services
    receiver = control.ReceiverController()
    receiver.configure("Linux services")
    receiver.close(release_local_service=False)
    assert events == []


@pytest.mark.xfail(strict=True, reason=(
    "Known main REG-03 gap: exit release=True stops pre-existing "
    "readsb/tar1090 instead of preserving externally owned services"))
def test_external_readsb_should_survive_exit_release_opt_in(fake_services):
    events, _ = fake_services
    receiver = control.ReceiverController()
    receiver.configure("Linux services")
    receiver._service_started_by_app = False
    receiver.close(release_local_service=True)
    assert events == [], "Exit must never stop a receiver owned by another app"


def test_explicit_stop_uses_shared_service_action(fake_services):
    events, _ = fake_services
    receiver = control.ReceiverController()
    receiver.configure("Linux services")
    receiver.stop()
    assert events == ["stop"]
    assert not receiver._service_started_by_app


def test_start_with_preexisting_service_does_not_claim_ownership(fake_services):
    events, _ = fake_services
    receiver = control.ReceiverController()
    receiver.configure("Linux services")
    receiver.start()
    assert events == ["start"]
    assert receiver._service_started_by_app is False


def test_start_after_inactive_service_records_app_ownership(fake_services):
    events, active = fake_services
    active["readsb.service"] = False
    receiver = control.ReceiverController()
    receiver.configure("Linux services")
    receiver.start()
    assert events == ["start"]
    assert receiver._service_started_by_app is True


def test_failed_start_does_not_claim_service(monkeypatch, fake_services):
    receiver = control.ReceiverController()
    receiver.configure("Linux services")
    monkeypatch.setattr(control, "service_action",
                        lambda action: (_ for _ in ()).throw(DataError("fake failure")))
    with pytest.raises(DataError, match="fake failure"):
        receiver.start()
    assert receiver._service_started_by_app is False


def test_remote_exit_never_stops_local_even_if_release_enabled(fake_services):
    events, _ = fake_services
    receiver = control.ReceiverController()
    receiver.configure("Remote JSON", "http://127.0.0.1:3000/aircraft.json")
    receiver.close(release_local_service=True)
    assert events == []


def test_service_stop_builds_restricted_argv_without_systemctl(monkeypatch):
    invocations = []
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_verify_transition", lambda action: None)
    def fake_run(argv, **kwargs):
        invocations.append((list(argv), kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(control.subprocess, "run", fake_run)
    result = control.service_action("stop")
    assert result.startswith("Decoder stopped")
    assert len(invocations) == 1
    assert invocations[0][0] == [
        "/usr/bin/sudo", "-n", "/usr/bin/systemctl",
        "stop", "readsb.service", "tar1090.service"]
    assert invocations[0][1]["check"] is False
