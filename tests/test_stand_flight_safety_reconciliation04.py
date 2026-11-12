"""STAND-FLIGHT-SAFETY-RECONCILIATION-04: visible, truthful shared-service Quit.

Use only synthetic receiver/service states and AST-extracted Qt closeEvent
methods; never import a live WebEngine, open sockets, contact hardware,
run systemctl/sudo, start external applications or touch user settings.
"""
from __future__ import annotations

import ast
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tihulu_flight_radar import control


class _FakeQWindow:
    def closeEvent(self, event):
        event.completed.append("base-close")


def _synthetic_qt_window(filename, class_name, **namespace):
    """Execute the actual Qt closeEvent method inside an inert class shell.

    Preserve its real super() call and method body without Qt or WebEngine
    import side effects. This is not a copy of the implementation.
    """
    source = Path(__file__).resolve().parents[1] / "tihulu_flight_radar" / filename
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    original = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node for node in original.body
        if isinstance(node, ast.FunctionDef) and node.name == "closeEvent"
    )
    wrapper = ast.ClassDef(
        name=class_name,
        bases=[ast.Name(id="_FakeQWindow", ctx=ast.Load())],
        keywords=[],
        body=[method],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    scope = {"__builtins__": __builtins__, "_FakeQWindow": _FakeQWindow,
             "time": time, **namespace}
    exec(compile(module, str(source), "exec"), scope)
    return scope[class_name]()


def test_service_mode_quit_records_truthful_partial_release_without_service_io(
        monkeypatch):
    monkeypatch.setattr(control.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        control, "service_action",
        lambda _: pytest.fail("Global Stop must not be attempted"),
    )
    controller = control.ReceiverController()
    controller.close(release_local_service=True)
    assert controller._closed
    assert controller.last_service_release_note
    assert "were not stopped" in controller.last_service_release_note
    assert "other receiver" in controller.last_service_release_note


def test_native_ui_displays_shared_receiver_preservation_warning_on_clean_quit():
    notices, events = [], []
    QMessageBox = SimpleNamespace(
        warning=lambda _window, title, body: notices.append((title, body))
    )
    window = _synthetic_qt_window(
        "native.py", "NativeRadarWindow",
        QMessageBox=QMessageBox,
        QUrl=lambda value: value,
        MixedOwnershipWarning=control.MixedOwnershipWarning,
    )
    window._quit_done = False
    window._exit_requested = False
    window._quit_deadline = None
    window._quit_warning_shown = False
    window._startup_future = None
    window.classic_window = None
    window.bridge = SimpleNamespace(
        request_quit=lambda: events.append("quit-gate"),
        close=lambda **kw: events.append(("receiver-close", kw)),
        receiver=SimpleNamespace(
            last_service_release_note="Shared readsb/tar1090 were not stopped."
        ),
    )
    window._startup_timer = SimpleNamespace(stop=lambda: events.append("timer"))
    window._startup_pool = SimpleNamespace(
        shutdown=lambda **kw: events.append(("shutdown", kw))
    )
    window._close_local_listener = lambda: events.append("listener")
    window.release_action = SimpleNamespace(isChecked=lambda: True)
    window.web = SimpleNamespace(
        _popups=[],
        setUrl=lambda url: events.append(("web-url", url)),
    )
    event = SimpleNamespace(
        completed=[], ignore=lambda: events.append("ignore")
    )

    window.closeEvent(event)

    assert window._quit_done
    assert event.completed == ["base-close"]
    assert "ignore" not in events
    assert notices == [
        ("Shared receiver preserved", "Shared readsb/tar1090 were not stopped.")
    ]
    assert ("receiver-close", {"release_local_service": True}) in events


def test_classic_ui_displays_shared_receiver_preservation_warning_on_clean_quit():
    notices, events = [], []
    QMessageBox = SimpleNamespace(
        warning=lambda _window, title, body: notices.append((title, body))
    )
    window = _synthetic_qt_window(
        "app.py", "RadarWindow",
        QMessageBox=QMessageBox,
        MixedOwnershipWarning=control.MixedOwnershipWarning,
        DataError=control.DataError,
    )
    window._quit_done = False
    window._quit_requested = False
    window._quit_deadline = None
    window._quit_warning_shown = False
    window._owns_receiver = True
    window.timer = SimpleNamespace(stop=lambda: events.append("timer"))
    window.controller = SimpleNamespace(
        request_quit=lambda: events.append("quit-gate"),
        close=lambda **kw: events.append(("receiver-close", kw)),
        last_service_release_note="Shared readsb/tar1090 were not stopped.",
    )
    window.action_future = None
    window.snapshot_future = None
    window.map_future = None
    window._quit_retry = SimpleNamespace(stop=lambda: events.append("retry-stop"))
    window.pool = SimpleNamespace(
        shutdown=lambda **kw: events.append(("shutdown", kw))
    )
    window.release_checkbox = SimpleNamespace(isChecked=lambda: True)
    window.map_server = SimpleNamespace(close=lambda: events.append("map-close"))
    window._map_dialogs = []
    event = SimpleNamespace(completed=[], ignore=lambda: events.append("ignore"))

    window.closeEvent(event)

    assert window._quit_done
    assert event.completed == ["base-close"]
    assert "ignore" not in events
    assert notices == [
        ("Shared receiver preserved", "Shared readsb/tar1090 were not stopped.")
    ]
    assert ("receiver-close", {"release_local_service": True}) in events
