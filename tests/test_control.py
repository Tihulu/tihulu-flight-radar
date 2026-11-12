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


def test_restart_calls_stop_then_start(monkeypatch):
    receiver = ReceiverController()
    # Restart is permitted for app-owned Direct readsb, not unowned systemd.
    receiver.configure("Direct readsb")
    calls = []
    monkeypatch.setattr(receiver, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(receiver, "start", lambda: calls.append("start") or "started")
    assert receiver.restart() == "started"
    assert calls == ["stop", "start"]


def test_stable_transition_rejects_transient_active(monkeypatch):
    import tihulu_flight_radar.control as control

    states = iter([(True, "active"), (False, "failed"), (False, "failed")])
    monkeypatch.setattr(control, "_unit_active", lambda _: next(states, (False, "failed")))
    now = [0.0]
    monkeypatch.setattr(control.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(control.time, "sleep", lambda duration: now.__setitem__(0, now[0] + duration))
    with pytest.raises(DataError, match="failed to stay active"):
        control._verify_transition("start", timeout_seconds=0.75)


def test_direct_readsb_does_not_compete_with_systemd(monkeypatch):
    import tihulu_flight_radar.control as control

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True, "active"))
    receiver = ReceiverController()
    receiver.configure("Direct readsb")
    with pytest.raises(DataError, match="already owns the SDR"):
        receiver.start()


def test_shared_service_stays_running_when_exit_release_disabled(monkeypatch):
    import tihulu_flight_radar.control as control

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True, "active"))
    operations = []
    monkeypatch.setattr(control, "service_action", lambda action: operations.append(action))
    receiver = ReceiverController()
    receiver.configure("Linux services")
    receiver._service_started_by_app = True
    receiver.close(release_local_service=False)
    assert operations == [], "User disabled service release; app ownership must not override it"


def test_shared_service_is_never_stopped_automatically_on_exit(monkeypatch):
    import tihulu_flight_radar.control as control

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True, "active"))
    operations = []
    monkeypatch.setattr(control, "service_action", lambda action: operations.append(action))
    receiver = ReceiverController()
    receiver.configure("Linux services")
    receiver.close(release_local_service=True)
    assert operations == [], "Automatic exit must not stop shared readsb or tar1090"


def test_exit_never_stops_external_remote_json_services(monkeypatch):
    import tihulu_flight_radar.control as control

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True, "active"))
    operations = []
    monkeypatch.setattr(control, "service_action", lambda action: operations.append(action))
    receiver = ReceiverController()
    receiver.configure("Remote JSON", "http://127.0.0.1:8080/data/aircraft.json")
    receiver.close(release_local_service=True)
    assert operations == []


def test_external_preexisting_service_start_is_read_only(monkeypatch):
    import tihulu_flight_radar.control as control

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True, "active"))
    commands = []
    monkeypatch.setattr(control, "service_action", lambda *a, **k: commands.append((a,k)))
    receiver = ReceiverController()
    msg = receiver.start()
    assert "monitoring" in msg
    assert commands == []
    assert not receiver._service_started_by_app


def test_external_service_refuses_stop_and_restart(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True, "active"))
    receiver = ReceiverController()
    with pytest.raises(DataError, match="globally shared"):
        receiver.stop()
    with pytest.raises(DataError, match="shared"):
        receiver.restart()


def test_explicit_ownership_flag_never_authorizes_shared_mutation(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    commands = []
    monkeypatch.setattr(control.subprocess, "run", lambda *a, **k: commands.append(a))
    for action in control.ACTIONS:
        for claimed in (False, True):
            with pytest.raises(DataError, match="read-only"):
                control.service_action(action, ownership_confirmed=claimed)
    assert not commands


def test_shared_service_start_when_inactive_is_refused(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (False, "inactive"))
    receiver = ReceiverController()
    with pytest.raises(DataError, match="read-only"):
        receiver.start()
    assert not receiver._service_started_by_app
    receiver.close(release_local_service=True)


def test_forged_in_process_owner_still_cannot_stop_or_restart_shared_service(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    receiver = ReceiverController()
    receiver._service_started_by_app = True
    with pytest.raises(DataError, match="globally shared"):
        receiver.stop()
    with pytest.raises(DataError, match="shared"):
        receiver.restart()
    receiver.close(release_local_service=True)
    assert not receiver._service_started_by_app


def test_changing_mode_forfeits_shared_service_ownership(monkeypatch):
    import tihulu_flight_radar.control as control

    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    receiver = ReceiverController()
    receiver._service_started_by_app = True
    receiver.configure("Remote JSON", "http://127.0.0.1:8080/data/aircraft.json")
    assert not receiver._service_started_by_app
    receiver.configure("Linux services")
    with pytest.raises(DataError, match="globally shared"):
        receiver.stop()
