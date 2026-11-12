"""Adversarial read-only systemd tests. No machine services or SDR access."""
from pathlib import Path

import pytest

from tihulu_flight_radar import control
from tihulu_flight_radar.bridge import Bridge
from tihulu_flight_radar.core import DataError

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("action", ("start", "stop", "enable", "disable"))
@pytest.mark.parametrize("forged_ownership", (False, True))
def test_privilege_grant_flag_cannot_run_any_shared_service_action(
    monkeypatch, action, forged_ownership
):
    calls = []
    monkeypatch.setattr(control.subprocess, "run", lambda *args, **kw: calls.append((args, kw)))
    with pytest.raises(DataError, match="read-only"):
        control.service_action(action, ownership_confirmed=forged_ownership)
    assert not calls, "No subprocess, sudo or systemctl may execute"


@pytest.mark.parametrize("active", (True, False))
def test_linux_service_reader_has_no_mutating_actions(monkeypatch, active):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", lambda _name: (active, "active" if active else "inactive"))
    r = control.ReceiverController()
    r._service_started_by_app = True  # simulate a spoofed/reused historical flag
    if active:
        assert "monitoring" in r.start()
    else:
        with pytest.raises(DataError, match="read-only"):
            r.start()
    for action in (r.stop, r.restart):
        with pytest.raises(DataError, match="shared"):
            action()


@pytest.mark.parametrize("old_release_flag", (False, True))
def test_even_forged_owner_cannot_stop_services_on_close(monkeypatch, old_release_flag):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    called = []
    monkeypatch.setattr(control, "service_action", lambda *a, **k: called.append((a,k)))
    r = control.ReceiverController()
    r._service_started_by_app = True
    r.close(release_local_service=old_release_flag)
    assert not called
    assert not r._service_started_by_app


def test_direct_app_owned_child_is_still_released_on_exit(monkeypatch):
    r = control.ReceiverController()
    r.configure("Direct readsb")
    r.process = object()  # sentinel only, not a system subprocess
    stopped = []
    monkeypatch.setattr(r, "stop", lambda: stopped.append(True))
    r.close(release_local_service=True)
    assert stopped == [True]


def test_web_bridge_only_advertises_control_for_direct_process():
    bridge = Bridge(allow_control=True)
    assert bridge.receiver.mode in ("Direct readsb", "Linux services")
    if bridge.receiver.mode == "Linux services":
        assert bridge.receiver_state()["control_enabled"] is False
    bridge.receiver.configure("Direct readsb")
    assert bridge.receiver_state()["control_enabled"] is True
    bridge.receiver.configure("Remote JSON", "http://127.0.0.1/data/aircraft.json")
    assert bridge.receiver_state()["control_enabled"] is False


def test_classic_ui_and_installer_do_not_offer_shared_service_controls():
    classic = (REPO / "tihulu_flight_radar" / "app.py").read_text()
    native = (REPO / "tihulu_flight_radar" / "native.py").read_text()
    installer = (REPO / "scripts" / "install-linux.sh").read_text()
    assert 'self.boot_checkbox.setEnabled(False)' in classic
    assert 'mode == "Direct readsb"' in classic
    assert 'self.autostart_action.setEnabled(self.bridge.receiver.mode == "Direct readsb")' in native
    assert 'service_action, "enable"' not in classic
    assert "visudo" not in installer
    assert "sudo install -m 0440" not in installer
    assert "sudo systemctl" not in installer
