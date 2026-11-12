"""Isolated synthetic direct RTL-SDR lock contract; no hardware or services.

Only pytest-managed temporary paths, in-process fake children, and kernel file
locks against our own test file are used; never execute readsb/systemctl/sudo.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tihulu_flight_radar import control
from tihulu_flight_radar.core import DataError
from tihulu_flight_radar.direct_lease import DirectDeviceLease


@pytest.fixture
def isolated_root(monkeypatch, tmp_path):
    monkeypatch.setattr(DirectDeviceLease, "_directory", staticmethod(lambda: tmp_path))
    return tmp_path


def test_cooperating_second_direct_receiver_cannot_claim_held_lock(isolated_root):
    a = DirectDeviceLease()
    b = DirectDeviceLease()
    a.acquire()
    try:
        with pytest.raises(DataError, match="(?i)busy|lease"):
            b.acquire()
    finally:
        a.release()
    b.acquire()
    b.release()


def test_stale_lease_file_content_never_counts_as_live_process(isolated_root):
    a = DirectDeviceLease()
    a.acquire()
    a.release()
    lease_path = isolated_root / "rtlsdr-index-0.lock"
    assert lease_path.exists()
    # Kernel state, not PID files or stale JSON, is authoritative.
    lease_path.write_text('{"pid":99999,"boot_id":"stale"}', encoding="utf-8")
    b = DirectDeviceLease()
    b.acquire()
    b.release()


def test_unsafe_direct_lease_key_rejected():
    for key in ("../device", "../../etc", "USB:0", "", "a/b"):
        with pytest.raises(ValueError, match="Unsafe"):
            DirectDeviceLease(key)


def test_fake_symlink_lock_path_rejected_before_open(monkeypatch, isolated_root):
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink",
        lambda self: True if self.name == "rtlsdr-index-0.lock" else original(self),
    )
    with pytest.raises(DataError, match="(?i)unsafe|busy|lease"):
        DirectDeviceLease().acquire()
    assert not (isolated_root / "rtlsdr-index-0.lock").exists()


def test_global_service_stop_rejected_before_any_subprocess(monkeypatch):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        control.subprocess, "run",
        lambda *_a, **_k: pytest.fail("Never invoke real or fake systemctl"),
    )
    with pytest.raises(DataError, match="Shared readsb/tar1090"):
        control.service_action("stop")


def test_owned_direct_child_cleanup_releases_held_kernel_lease(isolated_root):
    events = []

    class Child:
        alive = True

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            events.append("terminate")
            self.alive = False

        def wait(self, timeout):
            events.append(("wait", timeout))
            return 0

        def kill(self):
            raise AssertionError("No kill needed")

    lease = DirectDeviceLease()
    lease.acquire()
    owner = control.ReceiverController()
    owner.mode = "Direct readsb"
    owner._direct_lease = lease
    owner.process = Child()
    owner._directory = SimpleNamespace(cleanup=lambda: events.append("cleanup"))
    owner.close(release_local_service=True)
    owner.close(release_local_service=True)

    assert events == ["terminate", ("wait", 5), "cleanup"]
    other = DirectDeviceLease()
    other.acquire()  # No stale held kernel claim after successful child cleanup.
    other.release()


def test_unreaped_owned_direct_child_retains_exclusive_lease_for_retry(
        isolated_root):
    events = []

    class StuckChild:
        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, timeout):
            events.append(("wait", timeout))
            raise subprocess.TimeoutExpired(cmd="synthetic-only", timeout=timeout)

        def kill(self):
            events.append("kill")

    lease = DirectDeviceLease()
    lease.acquire()
    owner = control.ReceiverController()
    owner.mode = "Direct readsb"
    owner._direct_lease = lease
    owner.process = StuckChild()
    owner._directory = SimpleNamespace(cleanup=lambda: events.append("cleanup"))

    try:
        with pytest.raises(DataError, match="did not exit"):
            owner.close(release_local_service=True)
        with pytest.raises(DataError, match="(?i)busy|lease"):
            DirectDeviceLease().acquire()
        assert "cleanup" not in events
        assert owner.process is not None and owner._direct_lease is lease
    finally:
        # No real process exists; release only our synthetic kernel file lock.
        lease.release()


def test_shared_service_quit_preserves_pair_even_after_app_start(monkeypatch):
    """No special test fixture metadata can justify automatic systemd Stop."""
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    state = {unit: "inactive" for unit in control.UNITS}
    actions = []
    monkeypatch.setattr(
        control, "_unit_active",
        lambda unit: (state[unit] == "active", state[unit]),
    )

    def fake_action(action):
        actions.append(action)
        if action == "start":
            state.update({u: "active" for u in state})
        elif action == "stop":
            pytest.fail("Shared-service Quit must not call any global Stop")
        return "fake " + action

    monkeypatch.setattr(control, "service_action", fake_action)
    owner = control.ReceiverController()
    owner.start()
    owner.close(release_local_service=True)

    assert actions == ["start"]
    assert owner.last_service_release_note
    assert set(state.values()) == {"active"}
