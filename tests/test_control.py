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

def test_existing_service_is_not_claimed_on_app_start(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _: (True,"active"))
    called=[]
    monkeypatch.setattr(control, "service_action", lambda op: called.append(op))
    receiver=ReceiverController()
    message=receiver.start()
    assert "not owned" in message
    receiver.close()
    assert called==[]


def test_owned_linux_receiver_released_on_close(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    state={"active":False}
    def action(op):
        if op=="start":state["active"]=True
        elif op=="stop":state["active"]=False
        return op+" done"
    monkeypatch.setattr(control, "_unit_active", lambda _: (state["active"],"active" if state["active"] else "inactive"))
    calls=[]
    monkeypatch.setattr(control, "service_action", lambda op: calls.append(op) or action(op))
    monkeypatch.setattr(control, "_stop_only_app_owned_readsb",
                        lambda: calls.append("stop-readsb") or action("stop"))
    receiver=ReceiverController()
    receiver.start()
    assert receiver._started_service_in_app
    receiver.close()
    assert calls==["start","stop-readsb"]
    assert not state["active"]


def test_manual_stop_clears_exit_ownership(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform,"system",lambda:"Linux")
    state={"active":False}
    calls=[]
    def action(op):
        calls.append(op)
        state["active"]=op=="start"
        return op
    monkeypatch.setattr(control,"_unit_active",lambda _: (state["active"],"active" if state["active"] else "inactive"))
    monkeypatch.setattr(control,"service_action",action)
    receiver=ReceiverController()
    receiver.start()
    receiver.stop()
    receiver.close()
    assert calls==["start","stop"]


def test_close_failure_is_reported_and_not_silently_cleared(monkeypatch):
    import tihulu_flight_radar.control as control
    monkeypatch.setattr(control.platform,"system",lambda:"Linux")
    monkeypatch.setattr(control,"_unit_active",lambda _: (True,"active"))
    def failing():
        raise DataError("restricted sudo permission missing")
    monkeypatch.setattr(control,"_stop_only_app_owned_readsb",failing)
    receiver=ReceiverController()
    receiver._started_service_in_app=True
    with pytest.raises(DataError,match="restricted sudo"):
        receiver.close()
    assert receiver._started_service_in_app
