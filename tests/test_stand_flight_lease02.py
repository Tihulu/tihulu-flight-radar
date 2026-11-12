"""STAND-FLIGHT-LEASE-02: strict synthetic cross-application receiver safety.

Base: unchanged EXIT-01 PR #16, itself stacked on safety PR #15.
The earlier Internet-only foreign-owner case in PR #17 is ALREADY covered.

This file deliberately exposes NEW red shared-service ownership contracts.
Never xfail/skip/loosen the failing safety assertions to make CI green.
No real systemctl, sudo, receiver, installed application, network, driver,
USB device, service unit, Popen child or user's persistent files are used.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from tihulu_flight_radar import control
from tihulu_flight_radar.core import DataError


class SyntheticServicePair:
    """Deterministic in-memory systemd pair and independent app borrowers."""

    def __init__(self):
        self.states = {unit: "inactive" for unit in control.UNITS}
        self.invocation = {unit: 0 for unit in control.UNITS}
        self.borrowers = set()
        self.actions = []
        self.usb_owner = None

    def unit_active(self, unit):
        return self.states[unit] == "active", self.states[unit]

    def action(self, operation):
        self.actions.append(operation)
        if operation == "start":
            for unit in control.UNITS:
                if self.states[unit] != "active":
                    self.invocation[unit] += 1
                self.states[unit] = "active"
        elif operation == "stop":
            # Model the unsafe blast radius of a systemd paired Stop, even
            # when a foreign application is consuming the decoder.
            self.states.update({unit: "inactive" for unit in control.UNITS})
        return "mock " + operation

    def external_restart(self, unit):
        self.states[unit] = "active"
        self.invocation[unit] += 1


@pytest.fixture
def pair(monkeypatch):
    fake = SyntheticServicePair()
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(control, "_unit_active", fake.unit_active)
    monkeypatch.setattr(control, "service_action", fake.action)
    return fake


def test_flight_starts_pair_then_independent_tihulu_app_borrows_on_quit(pair):
    """Flight A starts both units; independent app B borrows AFTER the Start."""
    owner = control.ReceiverController()
    owner.start()
    foreign = {"app": "Synthetic Satellite Center", "running": True}
    pair.borrowers.add(foreign["app"])
    pair.usb_owner = "readsb.service"

    owner.close(release_local_service=True)

    assert pair.actions == ["start"], "Quit may not Stop a service used by B"
    assert set(pair.states.values()) == {"active"}
    assert pair.borrowers == {"Synthetic Satellite Center"}
    assert foreign["running"]


def test_second_flight_process_uses_first_process_service_without_takeover(pair):
    """Two independent controllers model two different Flight processes."""
    owner = control.ReceiverController()
    owner.start()
    borrower = control.ReceiverController()
    borrower.start()
    pair.borrowers.add("Flight process B")

    owner.close(release_local_service=True)

    assert pair.actions == ["start", "start"], (
        "Process A must not stop a shared decoder while process B is using it"
    )
    assert pair.states["readsb.service"] == "active"
    borrower.close(release_local_service=True)
    assert pair.actions == ["start", "start"]


def test_explicit_stop_must_not_interrupt_a_registered_foreign_borrower(pair):
    """Explicit user Stop remains offered, but cannot silently evict app B."""
    owner = control.ReceiverController()
    owner.start()
    pair.borrowers.add("Independent TIHULU app B")

    with pytest.raises(DataError, match="(?i)busy|borrow|lease|shared|owner"):
        owner.stop()

    assert pair.actions == ["start"], "No global paired Stop with live borrower"
    assert set(pair.states.values()) == {"active"}


def test_explicit_restart_must_not_stop_borrowed_receiver(pair):
    """Restart is Stop+Start; both actions need the same shared-lease guard."""
    owner = control.ReceiverController()
    owner.start()
    pair.borrowers.add("Independent TIHULU app B")

    with pytest.raises(DataError, match="(?i)busy|borrow|lease|shared|owner"):
        owner.restart()

    assert pair.actions == ["start"], "Restart may not stop B as an intermediate step"
    assert set(pair.states.values()) == {"active"}


@pytest.mark.parametrize("unit", control.UNITS)
def test_external_service_instance_restart_invalidates_app_owned_ledger(pair, unit):
    """An unrelated restart gives the unit a NEW InvocationID, not Flight's."""
    owner = control.ReceiverController()
    owner.start()
    original = pair.invocation[unit]
    pair.external_restart(unit)
    assert pair.invocation[unit] != original
    pair.borrowers.add("Independent app using externally restarted service")

    owner.close(release_local_service=True)

    assert pair.actions == ["start"], "Stale owner ledger must not stop new unit"
    assert pair.states[unit] == "active"


def test_stale_ownership_record_after_external_stop_never_issues_second_stop(pair):
    """An out-of-band Stop invalidates Flight's earlier service attribution."""
    owner = control.ReceiverController()
    owner.start()
    pair.states.update({unit: "inactive" for unit in control.UNITS})

    owner.close(release_local_service=True)

    assert pair.actions == ["start"], "Do not stop an already replaced/stopped pair"
    assert set(pair.states.values()) == {"inactive"}


def test_unknown_unit_identity_after_start_must_fail_closed(pair):
    """An unverifiable service state/identity cannot justify privileged Stop."""
    owner = control.ReceiverController()
    owner.start()
    pair.states["tar1090.service"] = "unknown"

    owner.close(release_local_service=True)

    assert pair.actions == ["start"], "Unknown unit identity is not owner proof"
    assert pair.states["tar1090.service"] == "unknown"


def test_direct_readsb_cannot_spawn_while_other_app_owns_usb(
        pair, monkeypatch, tmp_path):
    """Direct mode requires real exclusive-device coordination, not systemd status."""
    pair.usb_owner = "Synthetic Media Center"
    monkeypatch.setattr(control, "detect_sdr_processes", lambda: ["gqrx"])
    fake_binary = tmp_path / "mock-readsb"
    fake_binary.write_text("not an executable", encoding="utf-8")
    monkeypatch.setattr(
        control.tempfile, "TemporaryDirectory",
        lambda **_kw: SimpleNamespace(name=str(tmp_path), cleanup=lambda: None),
    )
    launches = []

    def forbidden_spawn(*args, **kwargs):
        launches.append((args, kwargs))
        raise AssertionError("Attempted to spawn a decoder on an externally owned USB")

    monkeypatch.setattr(control.subprocess, "Popen", forbidden_spawn)
    owner = control.ReceiverController()
    owner.configure("Direct readsb", decoder_path=str(fake_binary))

    with pytest.raises(DataError, match="(?i)busy|in use|owner|lease"):
        owner.start()

    assert launches == [], "Do not even attempt a direct readsb spawn"
    assert pair.usb_owner == "Synthetic Media Center"


def test_foreign_borrower_enrolls_while_flight_start_is_in_flight(
        pair, monkeypatch):
    """Barrier-controlled Start -> B borrows -> Quit; no sleep, no real workers."""
    entered = threading.Event()
    release = threading.Event()
    errors = []

    def gated_action(operation):
        outcome = pair.action(operation)
        if operation == "start":
            entered.set()
            if not release.wait(3):
                raise AssertionError("Synthetic Start barrier was not released")
        return outcome

    monkeypatch.setattr(control, "service_action", gated_action)
    owner = control.ReceiverController()

    def start_worker():
        try:
            owner.start()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=start_worker, daemon=True)
    thread.start()
    try:
        assert entered.wait(3), "Synthetic Start never entered"
        pair.borrowers.add("Independent app B registered during Start")
        owner.request_quit()
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive() and errors == []

    owner.close(release_local_service=True)

    assert pair.actions == ["start"], "Quit must revalidate B after Start finishes"
    assert set(pair.states.values()) == {"active"}


def test_preexisting_foreign_pair_is_not_assumed_owned_after_flight_start(pair):
    """Positive invariant from safety #15, not a repeat of PR #17's exact test."""
    pair.states.update({unit: "active" for unit in control.UNITS})
    owner = control.ReceiverController()
    owner.start()  # Harmless mocked Start request; both were already active.
    owner.close(release_local_service=True)

    assert pair.actions == ["start"]
    assert set(pair.states.values()) == {"active"}


@pytest.mark.parametrize("external", control.UNITS)
def test_mixed_ownership_preserves_preexisting_unit(pair, external):
    """Keep existing typed warning and paired-Stop refusal in #15/#16."""
    pair.states[external] = "active"
    owner = control.ReceiverController()
    owner.start()
    with pytest.raises(control.MixedOwnershipWarning, match="mixed ownership"):
        owner.close(release_local_service=True)

    assert pair.actions == ["start"]
    assert pair.states[external] == "active"


def test_unregistered_borrower_is_not_proof_of_exclusive_systemd_ownership(pair):
    """Noncooperating apps have NO lease record; passive Quit must still be safe."""
    owner = control.ReceiverController()
    owner.start()
    # Simulate a legacy/non-TIHULU client consuming systemd readsb without
    # participating in any optional cross-process TIHULU lease protocol.
    outsider = {"name": "independent decoder client", "receiver_active": True,
                "registered_in_lease": False}
    assert pair.borrowers == set()
    owner.close(release_local_service=True)

    assert pair.actions == ["start"], (
        "No lease record cannot prove no noncooperating receiver clients exist"
    )
    assert outsider["receiver_active"]
    assert set(pair.states.values()) == {"active"}


def test_owned_direct_child_is_reaped_once_without_touching_shared_services(pair):
    """Preserve complete Flight-owned cleanup even if systemd Stop is unsafe."""
    events = []

    class FakeChild:
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
            raise AssertionError("Graceful mock child must not be killed")

    owner = control.ReceiverController()
    owner.mode = "Direct readsb"
    owner.process = FakeChild()
    owner._directory = SimpleNamespace(cleanup=lambda: events.append("cleanup"))

    owner.close(release_local_service=True)
    owner.close(release_local_service=True)

    assert events == ["terminate", ("wait", 5), "cleanup"]
    assert owner.process is None and owner._directory is None
    assert pair.actions == [], "Owned child cleanup must not stop systemd"


def test_release_opt_out_keeps_service_pair_running(pair):
    """Preserve the owner's deliberate choice to keep local services active."""
    owner = control.ReceiverController()
    owner.start()
    owner.close(release_local_service=False)
    assert pair.actions == ["start"]
    assert set(pair.states.values()) == {"active"}


def test_known_foreign_sdr_process_blocks_systemd_start_without_process_call(
        monkeypatch):
    """Existing advisory conflict detection must remain an early guard."""
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        control, "_unit_active", lambda unit: (False, "inactive"))
    monkeypatch.setattr(control, "detect_sdr_processes", lambda: ["gqrx"])
    monkeypatch.setattr(
        control.subprocess, "run",
        lambda *_a, **_kw: pytest.fail("Systemctl/sudo must not be invoked"),
    )
    with pytest.raises(DataError, match="(?i)may be in use"):
        control.service_action("start")
