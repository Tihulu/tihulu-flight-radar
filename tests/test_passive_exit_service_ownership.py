"""Deterministic service-ownership safety tests; NO actual systemd/sudo/SDR.

The currently installed sudoers policy only permits the paired command.
Mixed ownership MUST NOT trigger a paired Stop; this conservatively preserves
foreign services and reports that an app-started unit may remain running.
"""
import subprocess
from types import SimpleNamespace

import pytest

import tihulu_flight_radar.control as control
from tihulu_flight_radar.core import DataError


@pytest.fixture
def fake_systemd(monkeypatch):
    states = {"readsb.service": "active", "tar1090.service": "active"}
    events = []

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active",
                        lambda unit: (states[unit] == "active", states[unit]))

    def fake_action(action):
        events.append(action)
        if action == "start":
            for unit in states:
                states[unit] = "active"
        elif action == "stop":
            for unit in states:
                states[unit] = "inactive"
        return "fake " + action

    monkeypatch.setattr(control, "service_action", fake_action)
    return states, events


def receiver():
    result = control.ReceiverController()
    result.configure("Linux services")
    return result


def test_external_both_active_passive_exit_on_never_stops(fake_systemd):
    states, events = fake_systemd
    r = receiver()
    r.close(release_local_service=True)
    assert events == []
    assert set(states.values()) == {"active"}


def test_existing_services_explicit_start_does_not_claim_them(fake_systemd):
    states, events = fake_systemd
    r = receiver()
    r.start()
    assert not r._service_units_started_by_app
    r.close(release_local_service=True)
    assert events == ["start"]
    assert set(states.values()) == {"active"}


def test_both_confirmed_inactive_started_by_app_are_released(fake_systemd):
    states, events = fake_systemd
    states.update({"readsb.service": "inactive", "tar1090.service": "inactive"})
    r = receiver()
    r.start()
    assert r._service_started_by_app
    assert r._service_units_started_by_app == set(control.UNITS)
    foreign_client = {"using_decoder": True}
    r.close(release_local_service=True)
    assert events == ["start"], "Historical Start does not prove exclusivity"
    assert set(states.values()) == {"active"}
    assert foreign_client["using_decoder"]
    assert r.last_service_release_note
    assert r._service_units_started_by_app == set()


def test_exit_opt_out_preserves_even_app_started_pair(fake_systemd):
    states, events = fake_systemd
    states.update({"readsb.service": "inactive", "tar1090.service": "inactive"})
    r = receiver()
    r.start()
    r.close(release_local_service=False)
    assert events == ["start"]
    assert set(states.values()) == {"active"}


@pytest.mark.parametrize("already_active", ["readsb.service", "tar1090.service"])
def test_mixed_ownership_never_issues_paired_stop(fake_systemd, already_active):
    states, events = fake_systemd
    other = next(unit for unit in states if unit != already_active)
    states[other] = "inactive"
    r = receiver()
    r.start()
    assert r._service_units_started_by_app == {other}
    with pytest.raises(DataError, match="mixed ownership"):
        r.close(release_local_service=True)
    assert events == ["start"]
    assert states[already_active] == "active"
    assert states[other] == "active", "Warn that app-started unit may still run"
    assert r._service_units_started_by_app == {other}


def test_unknown_unit_state_never_confers_ownership(fake_systemd):
    states, events = fake_systemd
    states.update({"readsb.service": "unknown", "tar1090.service": "unknown"})
    r = receiver()
    r.start()
    assert r._service_units_started_by_app == set()
    r.close(release_local_service=True)
    assert events == ["start"], "Unknown is not proof of ownership"


def test_repeated_start_does_not_erase_owned_pair(fake_systemd):
    states, events = fake_systemd
    states.update({"readsb.service": "inactive", "tar1090.service": "inactive"})
    r = receiver()
    r.start()
    r.start()
    assert r._service_units_started_by_app == set(control.UNITS)
    foreign_borrower = {"using_decoder": True}
    r.close(release_local_service=True)
    assert events == ["start", "start"]
    assert set(states.values()) == {"active"} and foreign_borrower["using_decoder"]
    assert r.last_service_release_note


def test_switch_to_remote_does_not_strand_app_started_pair(fake_systemd):
    states, events = fake_systemd
    states.update({"readsb.service": "inactive", "tar1090.service": "inactive"})
    r = receiver()
    r.start()
    r.configure("Remote JSON", "http://127.0.0.1:8080/data/aircraft.json")
    foreign_borrower = {"using_decoder": True}
    r.close(release_local_service=True)
    assert events == ["start"], "Switch to remote must not evict other users"
    assert set(states.values()) == {"active"} and foreign_borrower["using_decoder"]
    assert r.remote_url == "http://127.0.0.1:8080/data/aircraft.json"
    assert r.last_service_release_note


def test_failed_start_does_not_claim_inactive_units(monkeypatch, fake_systemd):
    states, events = fake_systemd
    states.update({"readsb.service": "inactive", "tar1090.service": "inactive"})
    def reject(action):
        raise DataError("simulated permission failure")
    monkeypatch.setattr(control, "service_action", reject)
    r = receiver()
    with pytest.raises(DataError, match="permission failure"):
        r.start()
    assert r._service_units_started_by_app == set()
    assert not r._service_started_by_app


def test_failed_exit_stop_retains_ownership_for_visible_error(monkeypatch, fake_systemd):
    """Genuine app-owned decoder cleanup failure must remain retryable and fatal."""
    states, events = fake_systemd
    states.update({"readsb.service": "inactive", "tar1090.service": "inactive"})
    r = receiver()
    r.start()
    failures = []
    cleanup = []

    class UnreapedDirectChild:
        def poll(self):
            return None

        def terminate(self):
            failures.append("terminate")

        def kill(self):
            failures.append("kill")

        def wait(self, *, timeout):
            failures.append(("wait", timeout))
            raise subprocess.TimeoutExpired(cmd="synthetic-direct-child", timeout=timeout)

    r.mode = "Direct readsb"
    r.process = UnreapedDirectChild()
    r._directory = SimpleNamespace(cleanup=lambda: cleanup.append("cleaned"))
    with pytest.raises(DataError, match="did not exit"):
        r.close(release_local_service=True)

    assert failures == ["terminate", ("wait", 5), "kill", ("wait", 3)]
    assert r.process is not None and cleanup == []
    assert not r._closed
    assert r._service_units_started_by_app == set(control.UNITS), (
        "Incomplete private cleanup must retain provenance for a safe retry"
    )
    assert events == ["start"], "Never mask failure by stopping global services"
    assert set(states.values()) == {"active"}


def test_explicit_stop_remains_user_requested_paired_action(fake_systemd):
    """Explicit shared service Stop remains available as a safe refusal."""
    states, events = fake_systemd
    foreign_borrower = {"connected": True, "using_receiver": True}
    r = receiver()
    with pytest.raises(DataError, match="(?i)shared|borrow|busy"):
        r.stop()
    assert events == [], "Do not issue privileged Stop even when requested"
    assert set(states.values()) == {"active"}
    assert foreign_borrower["connected"] and foreign_borrower["using_receiver"]
