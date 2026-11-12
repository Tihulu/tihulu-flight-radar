"""RQ-098 / EXIT-01: synthetic, owner-scoped full Quit regressions.

No actual sudo/systemctl, RF tuner, readsb executable, HTTP listener,
remote endpoint, Qt window, GPU context or user data is accessed.
"""
from __future__ import annotations

import subprocess
import threading
from types import SimpleNamespace

import pytest

from tihulu_flight_radar import bridge as bridge_module
from tihulu_flight_radar import control
from tihulu_flight_radar.core import DataError
from tihulu_flight_radar.map_server import LocalMapServer


@pytest.fixture
def services(monkeypatch):
    state = {"readsb.service": "active", "tar1090.service": "active"}
    events = []
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        control, "_unit_active",
        lambda name: (state[name] == "active", state[name]),
    )

    def action(name):
        events.append(name)
        if name == "start":
            state.update({key: "active" for key in state})
        if name == "stop":
            state.update({key: "inactive" for key in state})
        return "fake " + name

    monkeypatch.setattr(control, "service_action", action)
    return state, events


def test_external_services_preserved_and_no_late_start(services):
    state, events = services
    receiver = control.ReceiverController()
    receiver.close(release_local_service=True)
    receiver.close(release_local_service=True)
    assert events == []
    assert set(state.values()) == {"active"}
    with pytest.raises(DataError, match="shutting down"):
        receiver.start()
    with pytest.raises(DataError, match="shutting down"):
        receiver.restart()
    with pytest.raises(DataError, match="shutting down"):
        receiver.configure("Direct readsb")
    with pytest.raises(DataError, match="shutting down"):
        receiver.stop()


def test_app_started_pair_stops_once_on_repeated_quit(services):
    state, events = services
    state.update({name: "inactive" for name in state})
    receiver = control.ReceiverController()
    receiver.start()
    assert receiver._service_units_started_by_app == set(control.UNITS)
    receiver.close(release_local_service=True)
    receiver.close(release_local_service=True)
    assert events == ["start", "stop"]
    assert set(state.values()) == {"inactive"}
    assert receiver._closed


@pytest.mark.parametrize("external", control.UNITS)
def test_mixed_ownership_warning_and_no_external_stop(services, external):
    state, events = services
    state[next(name for name in state if name != external)] = "inactive"
    receiver = control.ReceiverController()
    receiver.start()
    with pytest.raises(DataError, match="mixed ownership"):
        receiver.close(release_local_service=True)
    with pytest.raises(DataError, match="mixed ownership"):
        receiver.close(release_local_service=True)
    assert events == ["start"]
    assert state[external] == "active"
    assert receiver._quit_requested.is_set()
    with pytest.raises(DataError, match="shutting down"):
        receiver.start()


def test_exit_opt_out_leaves_app_started_services(services):
    state, events = services
    state.update({name: "inactive" for name in state})
    receiver = control.ReceiverController()
    receiver.start()
    receiver.close(release_local_service=False)
    receiver.close(release_local_service=True)  # idempotent: don't override saved OFF
    assert events == ["start"]
    assert set(state.values()) == {"active"}


class FakeDirectChild:
    def __init__(self, *, stubborn=False, fail_kill=False):
        self.stubborn = stubborn
        self.fail_kill = fail_kill
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = []
        self.exited = False

    def poll(self):
        return 0 if self.exited else None

    def terminate(self):
        self.terminate_calls += 1
        if not self.stubborn:
            self.exited = True

    def kill(self):
        self.kill_calls += 1
        if not self.fail_kill:
            self.exited = True

    def wait(self, *, timeout):
        self.wait_calls.append(timeout)
        if not self.exited:
            raise subprocess.TimeoutExpired(cmd="mock-owned-readsb", timeout=timeout)
        return 0


def direct_receiver(monkeypatch, child):
    monkeypatch.setattr(control.platform, "system", lambda: "Windows")
    receiver = control.ReceiverController()
    receiver.configure("Direct readsb")
    directory = SimpleNamespace(cleanup=lambda: None)
    cleaned = []
    directory.cleanup = lambda: cleaned.append(True)
    receiver.process = child
    receiver._directory = directory
    return receiver, cleaned


@pytest.mark.parametrize("platform_name", ["Linux", "Windows", "Darwin"])
def test_only_direct_child_handle_terminated_and_reaped(monkeypatch, platform_name):
    child = FakeDirectChild()
    receiver, cleaned = direct_receiver(monkeypatch, child)
    monkeypatch.setattr(control.platform, "system", lambda: platform_name)
    monkeypatch.setattr(
        control, "service_action",
        lambda _: pytest.fail("Quit must not invoke paired systemd services"),
    )
    receiver.close(release_local_service=True)
    receiver.close(release_local_service=True)
    assert child.terminate_calls == 1
    assert child.kill_calls == 0
    assert child.wait_calls == [5]
    assert cleaned == [True]
    assert receiver.process is None
    assert receiver._directory is None


def test_direct_child_graceful_timeout_kills_exact_owned_handle(monkeypatch):
    child = FakeDirectChild(stubborn=True)
    receiver, cleaned = direct_receiver(monkeypatch, child)
    receiver.close()
    assert child.terminate_calls == 1
    assert child.kill_calls == 1
    assert child.wait_calls == [5, 3]
    assert cleaned == [True]


def test_unreaped_child_is_reported_and_handle_retained_for_retry(monkeypatch):
    child = FakeDirectChild(stubborn=True, fail_kill=True)
    receiver, cleaned = direct_receiver(monkeypatch, child)
    with pytest.raises(DataError, match="did not exit"):
        receiver.close()
    assert receiver.process is child
    assert cleaned == []
    assert not receiver._closed
    child.fail_kill = False
    receiver.close()
    assert receiver.process is None
    assert cleaned == [True]
    assert child.kill_calls == 2


def test_already_exited_child_is_reaped_and_temporary_dir_cleaned(monkeypatch):
    child = FakeDirectChild()
    child.exited = True
    receiver, cleaned = direct_receiver(monkeypatch, child)
    receiver.close()
    assert child.terminate_calls == 0
    assert child.wait_calls == [3]
    assert cleaned == [True]


def test_concurrent_start_and_quit_cannot_resurrect_services(monkeypatch, services):
    state, events = services
    state.update({name: "inactive" for name in state})
    inside_start = threading.Event()
    allow_start = threading.Event()
    errors = []

    def fake_action(operation):
        events.append(operation)
        if operation == "start":
            inside_start.set()
            if not allow_start.wait(2):
                raise DataError("simulated missing completion")
            state.update({name: "active" for name in state})
        else:
            state.update({name: "inactive" for name in state})
        return "fake " + operation

    monkeypatch.setattr(control, "service_action", fake_action)
    receiver = control.ReceiverController()

    def run_start():
        try:
            receiver.start()
        except Exception as exc:
            errors.append(exc)

    def run_close():
        try:
            receiver.close(release_local_service=True)
        except Exception as exc:
            errors.append(exc)

    startup = threading.Thread(target=run_start, daemon=True)
    closer = threading.Thread(target=run_close, daemon=True)
    startup.start()
    assert inside_start.wait(1)
    closer.start()
    assert receiver._quit_requested.wait(1)
    with pytest.raises(DataError, match="shutting down"):
        # Do not queue another Start behind a busy operation.
        # The gate is already set; the existing Start will eventually complete.
        if receiver._quit_requested.is_set():
            raise DataError("Receiver is shutting down")
    allow_start.set()
    startup.join(3)
    closer.join(3)
    assert not startup.is_alive() and not closer.is_alive()
    assert errors == []
    assert events == ["start", "stop"]
    assert set(state.values()) == {"inactive"}
    with pytest.raises(DataError, match="shutting down"):
        receiver.start()


def test_restart_interrupted_by_quit_cannot_issue_late_start(monkeypatch, services):
    state, events = services
    entered_stop = threading.Event()
    allow_stop = threading.Event()
    errors = []

    def fake_action(op):
        events.append(op)
        if op == "stop":
            entered_stop.set()
            if not allow_stop.wait(2):
                raise DataError("mock Stop expired")
            state.update({name: "inactive" for name in state})
        return "fake " + op

    monkeypatch.setattr(control, "service_action", fake_action)
    receiver = control.ReceiverController()

    def restart():
        try:
            receiver.restart()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=restart, daemon=True)
    thread.start()
    assert entered_stop.wait(1)
    receiver.request_quit()
    allow_stop.set()
    thread.join(3)
    receiver.close(release_local_service=True)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], DataError)
    assert "shutting down" in str(errors[0])
    assert events == ["stop"], "No service re-start after a Quit request"


def test_bridge_blocks_controls_and_snapshots_after_quit(monkeypatch):
    bridge = bridge_module.Bridge(allow_control=True)
    calls = []
    monkeypatch.setattr(bridge.receiver, "start", lambda: calls.append("start"))
    bridge.request_quit()
    with pytest.raises(DataError, match="shutting down"):
        bridge.control("start")
    with pytest.raises(DataError, match="shutting down"):
        bridge.snapshot("auto", 50.0, 6.0, 100)
    assert calls == []
    monkeypatch.setattr(bridge.receiver, "close", lambda **kwargs: calls.append("close"))
    bridge.close()
    assert calls == ["close"]


class FakeServer:
    def __init__(self):
        self.shutdowns = 0
        self.closes = 0

    def shutdown(self):
        self.shutdowns += 1

    def server_close(self):
        self.closes += 1


class FakeThread:
    def __init__(self, *, alive=False):
        self.alive = alive
        self.starts = 0
        self.joins = []

    def start(self):
        self.starts += 1

    def join(self, timeout=None):
        self.joins.append(timeout)

    def is_alive(self):
        return self.alive


def map_server_with_fakes(*, started=False, alive=False):
    listener = LocalMapServer.__new__(LocalMapServer)
    listener.httpd = FakeServer()
    listener.thread = FakeThread(alive=alive)
    listener._lifecycle_lock = threading.Lock()
    listener._started = started
    listener._closed = False
    return listener


def test_map_listener_close_before_start_is_bounded_and_repeatable():
    listener = map_server_with_fakes()
    listener.close()
    listener.close()
    assert listener.httpd.shutdowns == 0
    assert listener.httpd.closes == 1
    assert listener.thread.joins == []
    with pytest.raises(RuntimeError, match="closed"):
        listener.start()


def test_map_listener_close_reaps_only_owned_thread():
    listener = map_server_with_fakes()
    listener.start()
    listener.start()
    listener.close()
    listener.close()
    assert listener.thread.starts == 1
    assert listener.thread.joins == [3, 3]
    assert listener.httpd.shutdowns == 1
    assert listener.httpd.closes == 1


def test_map_listener_timeout_never_claims_thread_stopped():
    listener = map_server_with_fakes(started=True, alive=True)
    with pytest.raises(RuntimeError, match="did not stop"):
        listener.close()
    assert listener.httpd.closes == 1
    with pytest.raises(RuntimeError, match="did not stop"):
        listener.close()
    listener.thread.alive = False
    listener.close()
    assert listener.httpd.shutdowns == 1
    assert listener.httpd.closes == 1


def test_headless_bridge_quit_closes_only_its_local_listener(monkeypatch):
    events = []

    class SyntheticBridge:
        def __init__(self, **kwargs):
            self.token = "synthetic-token-not-used"
            self.allow_control = bool(kwargs.get("allow_control", False))
            events.append("bridge-created")

        def request_quit(self):
            events.append("quit-requested")

        def close(self):
            events.append("receiver-closed")

    class SyntheticHTTPServer:
        def __init__(self, addr, handler):
            self.server_port = addr[1]
            events.append("listener-created")

        def serve_forever(self, **kwargs):
            events.append("serve-returned")

        def server_close(self):
            events.append("listener-closed")

    monkeypatch.setattr(bridge_module, "Bridge", SyntheticBridge)
    monkeypatch.setattr(bridge_module, "ThreadingHTTPServer", SyntheticHTTPServer)
    bridge_module.main(["--port", "8510"])
    assert events[-4:] == [
        "serve-returned", "quit-requested", "listener-closed", "receiver-closed"
    ]
