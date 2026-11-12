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
    listener._request_condition = threading.Condition()
    listener._active_requests = 0
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

        def close(self, **kwargs):
            assert kwargs == {"release_local_service": True}
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


# Independent EXIT-01 QA follow-up: classification, bounded locks, HTTP
# request workers and read-only external-data preservation. All I/O below
# uses mocks and pytest's own temporary directory; no actual systemctl,
# receiver, network, installed app, or live HTTP server is touched.


@pytest.mark.parametrize("external_unit", control.UNITS)
def test_mixed_service_warning_is_typed_and_preserves_foreign_unit(
        services, external_unit):
    states, events = services
    owned = next(x for x in control.UNITS if x != external_unit)
    states[owned] = "inactive"
    receiver = control.ReceiverController()
    receiver.start()
    with pytest.raises(control.MixedOwnershipWarning, match="mixed ownership"):
        receiver.close(release_local_service=True)
    assert events == ["start"], "Passive Quit must never run a paired stop"
    assert states[external_unit] == "active"
    assert receiver._service_units_started_by_app == {owned}


def test_direct_failure_plus_mixed_is_fatal_not_harmless_warning(
        monkeypatch, services):
    states, events = services
    states["readsb.service"] = "inactive"
    receiver = control.ReceiverController()
    receiver.start()  # mixed: readsb app-owned, tar1090 external
    child = FakeDirectChild(stubborn=True, fail_kill=True)
    cleaned = []
    receiver.mode = "Direct readsb"
    receiver.process = child
    receiver._directory = SimpleNamespace(cleanup=lambda: cleaned.append(True))
    with pytest.raises(DataError, match="did not exit.*mixed ownership") as error:
        receiver.close(release_local_service=True)
    assert not isinstance(error.value, control.MixedOwnershipWarning)
    assert child.kill_calls == 1
    assert receiver.process is child and cleaned == []
    assert receiver._service_units_started_by_app == {"readsb.service"}
    assert states["tar1090.service"] == "active"
    assert events == ["start"], "Never use paired Stop on mixed ownership"


def test_quit_receiver_operation_lock_timeout_is_retryable(monkeypatch, services):
    states, events = services
    states.update({name: "inactive" for name in states})
    entered = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(control, "QUIT_OPERATION_TIMEOUT_SECONDS", 0.01)
    calls = []

    def fake_action(action):
        calls.append(action)
        if action == "start":
            entered.set()
            assert release.wait(2), "mock operation timed out"
            states.update({name: "active" for name in states})
        elif action == "stop":
            states.update({name: "inactive" for name in states})
        return "fake " + action

    monkeypatch.setattr(control, "service_action", fake_action)
    receiver = control.ReceiverController()
    errors = []

    def starter():
        try:
            receiver.start()
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=starter, daemon=True)
    worker.start()
    try:
        assert entered.wait(1)
        with pytest.raises(DataError, match="operation is still running"):
            receiver.close(release_local_service=True)
        assert receiver._quit_requested.is_set()
        assert not receiver._closed
        assert calls == ["start"]
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive() and errors == []
    receiver.close(release_local_service=True)
    assert calls == ["start", "stop"]
    assert set(states.values()) == {"inactive"}


def test_bridge_request_handler_ownership_registration_is_balanced(monkeypatch):
    bridge = bridge_module.Bridge()
    handler_cls = bridge_module.make_handler(bridge, 8510)
    calls = []
    monkeypatch.setattr(
        bridge_module.BaseHTTPRequestHandler, "handle",
        lambda _self: calls.append("handled"),
    )
    handler = handler_cls.__new__(handler_cls)
    handler.handle()
    assert calls == ["handled"]
    assert bridge._active_requests == 0
    bridge.request_quit()
    handler.handle()
    assert calls == ["handled"], "No new request after STOPPING"
    assert bridge._active_requests == 0


def test_bridge_http_request_drain_reports_partial_then_releases_caches(
        monkeypatch, tmp_path):
    bridge = bridge_module.Bridge()
    original_export = tmp_path / "user-export.json"
    original_export.write_text('{"saved":true}', encoding="utf-8")
    bridge.online.cached = [{"hex": "abcdef"}]
    bridge.multi_online.records["adsblol"] = {"rows": [{"hex": "abcdef"}]}
    mock_releases = []
    monkeypatch.setattr(
        bridge.receiver, "close",
        lambda **kwargs: mock_releases.append(kwargs),
    )
    assert bridge._begin_request()
    bridge.request_quit()
    with pytest.raises(DataError, match="active request"):
        bridge._wait_for_requests(timeout=0.01)
    monkeypatch.setattr(
        bridge, "_wait_for_requests",
        lambda: (_ for _ in ()).throw(DataError("1 active request, fake timeout"))
        if bridge._active_requests else None,
    )
    with pytest.raises(DataError, match="active request"):
        bridge.close()
    assert bridge.online.cached and bridge.multi_online.records
    bridge._end_request()
    bridge.close()
    assert bridge.online.cached == []
    assert bridge.multi_online.records == {}
    assert original_export.read_text(encoding="utf-8") == '{"saved":true}'
    assert len(mock_releases) == 2
    assert not bridge._begin_request(), "No late HTTP admission"


def test_bridge_close_receiver_lock_is_bounded(monkeypatch):
    bridge = bridge_module.Bridge()
    monkeypatch.setattr(bridge_module, "BRIDGE_LOCK_TIMEOUT_SECONDS", 0.01)
    entered = threading.Event()
    release = threading.Event()
    calls = []
    monkeypatch.setattr(bridge.receiver, "close", lambda **kwargs: calls.append("closed"))

    def other_request():
        with bridge.receiver_lock:
            entered.set()
            assert release.wait(2), "mock HTTP request timed out"

    worker = threading.Thread(target=other_request, daemon=True)
    worker.start()
    try:
        assert entered.wait(1)
        with pytest.raises(DataError, match="bridge command is still running"):
            bridge.close()
        assert bridge._quit_requested.is_set()
        assert calls == []
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    bridge.close()
    assert calls == ["closed"]


def test_remote_json_host_and_user_settings_survive_local_quit(
        monkeypatch, tmp_path, services):
    _, events = services
    saved = tmp_path / "recording.json"
    saved.write_bytes(b'{"saved":"owned by user"}')
    bridge = bridge_module.Bridge(allow_control=True)
    url = "https://remote.example.invalid/aircraft.json"
    bridge.receiver.configure("Remote JSON", url)
    monkeypatch.setattr(
        control, "read_remote",
        lambda _: pytest.fail("Quit must not contact a remote host"),
    )
    bridge.online.cached = [{"hex": "cafeda"}]
    bridge.close(release_local_service=True)
    assert bridge.receiver.remote_url == url
    assert saved.read_bytes() == b'{"saved":"owned by user"}'
    assert events == []
    assert bridge.online.cached == []
    with pytest.raises(DataError, match="shutting down"):
        bridge.control("start")


def _qt_method(filename, class_name, method_name, **scope):
    """Execute the *actual* Qt method AST with inert globals, no Qt import.

    Linux CI intentionally installs libEGL only after Python unit tests;
    importing the whole QWebEngine module here would exercise the runner,
    not the mocked Quit state machine. No test is skipped.
    """
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tihulu_flight_radar" / filename
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    cls = next(x for x in tree.body
               if isinstance(x, ast.ClassDef) and x.name == class_name)
    fn = next(x for x in cls.body
              if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
              and x.name == method_name)
    namespace = {"__builtins__": __builtins__, **scope}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"),
         namespace)
    return namespace[method_name]


def test_native_startup_timeout_warning_is_observed_without_second_close(
        monkeypatch):
    import time

    dialogs = []
    check = _qt_method(
        "native.py", "NativeRadarWindow", "_check_startup",
        QMessageBox=SimpleNamespace(warning=lambda *args: dialogs.append(args)),
        time=time,
    )
    fake = SimpleNamespace(
        _startup_future=SimpleNamespace(done=lambda: False),
        _exit_requested=True,
        _quit_deadline=0.0,
        _quit_warning_shown=False,
    )
    check(fake)
    check(fake)
    assert len(dialogs) == 1 and "Quit still draining" in dialogs[0][1]
    assert fake._quit_warning_shown


def test_native_local_listener_retryable_after_fake_thread_timeout():
    close_listener = _qt_method(
        "native.py", "NativeRadarWindow", "_close_local_listener",
    )
    server = FakeServer()
    thread = FakeThread(alive=True)
    window = SimpleNamespace(
        server=server, server_thread=thread, _listener_closed=False
    )
    with pytest.raises(RuntimeError, match="still alive"):
        close_listener(window)
    assert server.shutdowns == 1 and server.closes == 1
    assert window._listener_closed
    thread.alive = False
    close_listener(window)
    assert server.shutdowns == 1 and server.closes == 1
    assert thread.joins == [2, 2]


def test_native_combined_direct_failure_never_exits_as_mixed_only(monkeypatch):
    import time

    warnings = []
    close_window = _qt_method(
        "native.py", "NativeRadarWindow", "closeEvent",
        QMessageBox=SimpleNamespace(warning=lambda *args: warnings.append(args)),
        MixedOwnershipWarning=control.MixedOwnershipWarning,
        time=time,
    )
    ignored = []
    event = SimpleNamespace(ignore=lambda: ignored.append("ignored"))
    fake_bridge = SimpleNamespace(
        request_quit=lambda: None,
        close=lambda **kwargs: (_ for _ in ()).throw(
            DataError("app-owned readsb did not exit; mixed ownership warning")
        ),
    )
    window = SimpleNamespace(
        _quit_done=False,
        _exit_requested=False,
        _quit_deadline=None,
        _quit_warning_shown=False,
        _startup_future=None,
        classic_window=None,
        bridge=fake_bridge,
        _startup_timer=SimpleNamespace(stop=lambda: None),
        _startup_pool=SimpleNamespace(shutdown=lambda **kwargs: None),
        _close_local_listener=lambda: None,
        release_action=SimpleNamespace(isChecked=lambda: True),
    )
    close_window(window, event)
    assert ignored == ["ignored"]
    assert warnings and "did not exit" in warnings[0][2]
    assert not window._quit_done


def test_classic_combined_failure_never_exits_as_mixed_only(monkeypatch):
    import time

    warnings = []
    close_window = _qt_method(
        "app.py", "RadarWindow", "closeEvent",
        QMessageBox=SimpleNamespace(warning=lambda *args: warnings.append(args)),
        MixedOwnershipWarning=control.MixedOwnershipWarning,
        DataError=DataError,
        time=time,
    )
    ignored = []
    event = SimpleNamespace(ignore=lambda: ignored.append("ignored"))
    receiver = SimpleNamespace(
        request_quit=lambda: None,
        close=lambda **kwargs: (_ for _ in ()).throw(
            DataError("app-owned readsb did not exit; mixed ownership warning")
        ),
    )
    window = SimpleNamespace(
        _quit_done=False, _quit_requested=False, _quit_deadline=None,
        _quit_warning_shown=False, timer=SimpleNamespace(stop=lambda: None),
        controller=receiver, _owns_receiver=True,
        action_future=None, snapshot_future=None, map_future=None,
        _quit_retry=SimpleNamespace(stop=lambda: None),
        pool=SimpleNamespace(shutdown=lambda **kwargs: None),
        release_checkbox=SimpleNamespace(isChecked=lambda: True),
        map_server=SimpleNamespace(close=lambda: None),
    )
    close_window(window, event)
    assert ignored == ["ignored"]
    assert warnings and "did not exit" in warnings[0][2]
    assert not window._quit_done

def test_map_listener_reports_active_request_and_rechecks_on_retry(monkeypatch):
    listener = map_server_with_fakes(started=True)
    assert listener._begin_request()
    # An immediate fake wait is deterministic: no 3-second CI delay or port.
    monkeypatch.setattr(
        listener._request_condition, "wait_for",
        lambda predicate, timeout: predicate(),
    )
    with pytest.raises(RuntimeError, match="request workers still active"):
        listener.close()
    assert listener.httpd.shutdowns == 1
    assert listener.httpd.closes == 1
    assert not listener._begin_request(), "Closed listener cannot admit work"
    listener._end_request()
    listener.close()  # Retry must verify the prior owned handler completed.
    assert listener._active_requests == 0
    assert listener.httpd.closes == 1


def test_map_handler_request_registry_cannot_underflow_after_repeated_quit():
    listener = map_server_with_fakes(started=False)
    assert listener._begin_request()
    listener._end_request()
    listener.close()
    listener.close()
    assert listener._active_requests == 0
    assert not listener._begin_request()


def test_headless_quit_external_service_safety_and_mixed_warning(
        monkeypatch, services, capsys):
    """CLI exits do not invoke paired Stop for foreign/mixed service units."""
    states, events = services
    states["tar1090.service"] = "inactive"
    instances = []

    class FakeBridge(bridge_module.Bridge):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            instances.append(self)

    class FakeHTTP:
        daemon_threads = True

        def __init__(self, addr, handler):
            self.server_port = addr[1]

        def serve_forever(self, **kwargs):
            # A user explicitly pressed Start before companion Quit.
            instances[-1].control("start")

        def server_close(self):
            pass

    monkeypatch.setattr(bridge_module, "Bridge", FakeBridge)
    monkeypatch.setattr(bridge_module, "ThreadingHTTPServer", FakeHTTP)
    bridge_module.main(["--port", "8510", "--allow-control"])
    assert events == ["start"], "Mixed ownership cannot use paired Stop"
    assert states["readsb.service"] == "active"
    assert "mixed ownership" in capsys.readouterr().err
    assert instances[0].receiver._quit_requested.is_set()


def test_headless_quit_releases_app_owned_paired_systemd_only(
        monkeypatch, services):
    states, events = services
    states.update({name: "inactive" for name in states})
    instances = []

    class FakeBridge(bridge_module.Bridge):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            instances.append(self)

    class FakeHTTP:
        daemon_threads = True

        def __init__(self, addr, handler):
            self.server_port = addr[1]

        def serve_forever(self, **kwargs):
            instances[-1].control("start")

        def server_close(self):
            pass

    monkeypatch.setattr(bridge_module, "Bridge", FakeBridge)
    monkeypatch.setattr(bridge_module, "ThreadingHTTPServer", FakeHTTP)
    bridge_module.main(["--port", "8510", "--allow-control"])
    assert events == ["start", "stop"]
    assert set(states.values()) == {"inactive"}
    assert instances[0].receiver._quit_requested.is_set()


def test_queued_start_is_rejected_after_quit_even_if_executor_runs_it(
        monkeypatch, services):
    """Synthetic Qt-style queued Start cannot acquire a receiver after STOPPING."""
    from concurrent.futures import ThreadPoolExecutor

    _, events = services
    gate = threading.Event()
    entered = threading.Event()
    controller = control.ReceiverController()

    def blocking_first_job():
        entered.set()
        assert gate.wait(2), "fake queued worker did not finish"

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(blocking_first_job)
        assert entered.wait(1)
        queued_start = pool.submit(controller.start)
        controller.request_quit()  # event set before worker may start
        gate.set()
        first.result(timeout=2)
        with pytest.raises(DataError, match="shutting down"):
            queued_start.result(timeout=2)
    controller.close(release_local_service=True)
    assert events == [], "Queued Start must not touch external systemd services"


def test_shutdown_caches_are_owned_memory_not_saved_user_exports(
        monkeypatch, tmp_path):
    """No remote API call, delete, or cache-to-recording spill on Quit."""
    bridge = bridge_module.Bridge()
    exported = tmp_path / "completed-flight-data.json"
    exported.write_bytes(b"previously saved recording")
    bridge.online.cached = [{"hex": "deadc0", "seen": 0}]
    bridge.multi_online.records = {"adsblol": {"rows": [{"hex": "deadc0"}]}}
    monkeypatch.setattr(bridge.receiver, "close", lambda **kwargs: None)
    bridge.close(release_local_service=True)
    assert bridge.online.cached == []
    assert bridge.multi_online.records == {}
    assert exported.read_bytes() == b"previously saved recording"


# Final integration-safety coverage. These tests use the existing real Qt
# method bodies via _qt_method, but never load Qt, open SDR/HTTP sockets,
# spawn a subprocess, call sudo/systemctl, or access a real remote host.


def test_shared_classic_window_closes_only_its_owned_map_and_workers():
    """A secondary native classic view is a borrower of its parent receiver."""
    import time

    events = []
    receiver = SimpleNamespace(
        request_quit=lambda: pytest.fail("borrowed controller must not enter Quit"),
        close=lambda **kw: pytest.fail("borrowed controller must not be released"),
    )
    classic_close = _qt_method(
        "app.py", "RadarWindow", "closeEvent",
        time=time, DataError=DataError,
        MixedOwnershipWarning=control.MixedOwnershipWarning,
        QMessageBox=SimpleNamespace(warning=lambda *a: pytest.fail(str(a))),
        super=lambda: SimpleNamespace(
            closeEvent=lambda event: events.append("classic-qt-close")),
    )
    secondary = SimpleNamespace(
        _quit_done=False, _quit_requested=False, _quit_deadline=None,
        _quit_warning_shown=False, _owns_receiver=False, controller=receiver,
        timer=SimpleNamespace(stop=lambda: events.append("classic-timer-stop")),
        action_future=None, snapshot_future=None, map_future=None,
        _quit_retry=SimpleNamespace(
            stop=lambda: events.append("classic-retry-stop")),
        pool=SimpleNamespace(shutdown=lambda **kw: events.append(
            ("classic-pool-stop", kw["wait"], kw["cancel_futures"]))),
        map_server=SimpleNamespace(close=lambda: events.append("classic-map-close")),
        _map_dialogs=[SimpleNamespace(close=lambda: events.append("map-dialog-close"))],
    )
    ignored = []
    event = SimpleNamespace(ignore=lambda: ignored.append("ignored"))
    classic_close(secondary, event)
    assert ignored == []
    assert secondary._quit_done and secondary._quit_requested
    assert ("classic-pool-stop", True, True) in events
    assert events.index("classic-map-close") < events.index("classic-qt-close")
    assert events.count("classic-map-close") == 1
    classic_close(secondary, event)
    assert events.count("classic-map-close") == 1, "Repeated close is idempotent"


def test_native_quit_drains_shared_classic_then_reaps_only_owned_child(monkeypatch):
    """Full native Quit uses one controller, and does not kill another SDR client."""
    import time

    monkeypatch.setattr(control.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        control, "service_action",
        lambda action: pytest.fail("Quit may not touch external systemd services"))
    bridge = bridge_module.Bridge(allow_control=True)
    bridge.receiver.configure("Direct readsb")
    ours = FakeDirectChild()
    independent = FakeDirectChild()
    bridge.receiver.process = ours
    released = []
    bridge.receiver._directory = SimpleNamespace(
        cleanup=lambda: released.append("owned-json-dir"))

    actions = []
    classic_close = _qt_method(
        "app.py", "RadarWindow", "closeEvent",
        time=time, DataError=DataError,
        MixedOwnershipWarning=control.MixedOwnershipWarning,
        QMessageBox=SimpleNamespace(warning=lambda *a: pytest.fail(str(a))),
        super=lambda: SimpleNamespace(
            closeEvent=lambda event: actions.append("classic-qt-close")),
    )
    classic_ignored = []
    classic = SimpleNamespace(
        _quit_done=False, _quit_requested=False, _quit_deadline=None,
        _quit_warning_shown=False, _owns_receiver=False,
        controller=bridge.receiver,
        timer=SimpleNamespace(stop=lambda: None),
        action_future=None, snapshot_future=None, map_future=None,
        _quit_retry=SimpleNamespace(stop=lambda: None),
        pool=SimpleNamespace(shutdown=lambda **kw: actions.append("classic-pool")),
        map_server=SimpleNamespace(close=lambda: actions.append("classic-map")),
        _map_dialogs=[],
    )

    def close_classic():
        actions.append("classic-quit")
        classic_close(classic, SimpleNamespace(
            ignore=lambda: classic_ignored.append("ignore")))
        return not classic_ignored

    server = SimpleNamespace(
        shutdown=lambda: actions.append("native-http-shutdown"),
        server_close=lambda: actions.append("native-socket-closed"),
    )
    thread = FakeThread(alive=False)
    popup = SimpleNamespace(close=lambda: actions.append("popup-closed"))
    web = SimpleNamespace(
        _popups=[popup], setUrl=lambda url: actions.append(("web-url", url)))
    native_listener_close = _qt_method(
        "native.py", "NativeRadarWindow", "_close_local_listener")
    native_close = _qt_method(
        "native.py", "NativeRadarWindow", "closeEvent",
        time=time, QUrl=lambda url: url,
        MixedOwnershipWarning=control.MixedOwnershipWarning,
        QMessageBox=SimpleNamespace(warning=lambda *a: pytest.fail(str(a))),
        super=lambda: SimpleNamespace(
            closeEvent=lambda event: actions.append("native-qt-close")),
    )
    native = SimpleNamespace(
        _quit_done=False, _exit_requested=False, _quit_deadline=None,
        _quit_warning_shown=False, _startup_future=None, bridge=bridge,
        classic_window=SimpleNamespace(close=close_classic),
        _startup_timer=SimpleNamespace(stop=lambda: actions.append("startup-stop")),
        _startup_pool=SimpleNamespace(shutdown=lambda **kw: actions.append(
            ("native-pool", kw["wait"], kw["cancel_futures"]))),
        _listener_closed=False, server=server, server_thread=thread,
        release_action=SimpleNamespace(isChecked=lambda: True), web=web,
    )
    native._close_local_listener = lambda: native_listener_close(native)
    ignored = []
    event = SimpleNamespace(ignore=lambda: ignored.append("ignored"))
    native_close(native, event)

    assert ignored == [] and classic_ignored == []
    assert native._quit_done and classic._quit_done
    assert native._listener_closed and bridge._quit_requested.is_set()
    assert bridge.receiver._quit_requested.is_set()
    assert actions.index("classic-map") < actions.index("native-http-shutdown")
    assert ("native-pool", True, True) in actions
    assert actions.count("native-http-shutdown") == 1
    assert actions.count("native-socket-closed") == 1
    assert thread.joins == [2]
    assert ("web-url", "about:blank") in actions
    assert ours.terminate_calls == 1 and ours.wait_calls == [5]
    assert ours.exited and bridge.receiver.process is None
    assert released == ["owned-json-dir"]
    assert independent.terminate_calls == independent.kill_calls == 0
    assert independent.wait_calls == [] and not independent.exited

    native_close(native, event)
    assert actions.count("native-http-shutdown") == 1
    assert actions.count("classic-quit") == 1
    assert ours.terminate_calls == 1 and ours.wait_calls == [5]


def test_two_borrowers_of_external_pair_quit_without_stopping_any_unit(services):
    """Independent read-only watchers do not gain service shutdown ownership."""
    states, events = services
    first = bridge_module.Bridge(allow_control=True)
    second = bridge_module.Bridge(allow_control=True)
    assert first.receiver is not second.receiver
    assert first.receiver._service_units_started_by_app == set()
    assert second.receiver._service_units_started_by_app == set()
    first.close(release_local_service=True)
    assert states == {"readsb.service": "active", "tar1090.service": "active"}
    second.close(release_local_service=True)
    first.close(release_local_service=True)
    assert events == [], "Neither borrower may issue a paired service Stop"
    assert first.receiver._closed and second.receiver._closed


def test_explicit_start_claims_pair_but_second_observer_quit_only_borrows(services):
    """One owner and a subsequently observing client are tracked separately.

    This is a *sequential* case: the borrower quits BEFORE the owner.
    Concurrent cross-process leases are not implemented or certified here.
    """
    states, events = services
    states.update({unit: "inactive" for unit in states})
    owner = control.ReceiverController()
    observer = control.ReceiverController()
    owner.start()
    observer.start()
    assert owner._service_units_started_by_app == set(control.UNITS)
    assert observer._service_units_started_by_app == set()
    observer.close(release_local_service=True)
    assert states == {"readsb.service": "active", "tar1090.service": "active"}
    assert events == ["start", "start"]
    owner.close(release_local_service=True)
    assert events == ["start", "start", "stop"]


def test_local_direct_child_quit_does_not_touch_foreign_direct_child(monkeypatch):
    ours = FakeDirectChild(stubborn=True)
    independent = FakeDirectChild()
    receiver, cleaned = direct_receiver(monkeypatch, ours)
    monkeypatch.setattr(
        control, "service_action",
        lambda action: pytest.fail("No global service action on direct Quit"))
    receiver.close(release_local_service=True)
    assert ours.terminate_calls == 1 and ours.kill_calls == 1
    assert ours.wait_calls == [5, 3]
    assert receiver.process is None and cleaned == [True]
    assert independent.terminate_calls == independent.kill_calls == 0
    assert independent.wait_calls == [] and not independent.exited
