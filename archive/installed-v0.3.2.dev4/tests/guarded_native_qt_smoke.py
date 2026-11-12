#!/usr/bin/env python3
"""Guarded native Qt WebEngine window smoke, GitHub CI only.

No physical SDR, no user XDG settings, no readsb/tar1090 control and no
automatic geolocation permission. Does not claim full playback/data parity.
"""
from __future__ import annotations

import os
from pathlib import Path

runner = os.environ.get("RUNNER_TEMP", "")
expected_home = runner + "/installed-snapshot-home"
if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    raise RuntimeError("Only offscreen CI Qt is allowed")
if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("CI"):
    raise RuntimeError("CI required; do not run on owner's workstation")
if not runner or os.environ.get("HOME") != expected_home:
    raise RuntimeError("Must use ephemeral CI HOME")
for name, suffix in (
    ("XDG_CONFIG_HOME", "/.config"),
    ("XDG_DATA_HOME", "/.local/share"),
    ("XDG_CACHE_HOME", "/.cache"),
):
    if os.environ.get(name) != expected_home + suffix:
        raise RuntimeError("Refusing to touch uncontrolled XDG path: " + name)
if not Path(expected_home).is_dir():
    raise RuntimeError("CI profile directory is missing")

import tihulu_flight_radar.control as control


def deny(*_args, **_kwargs):
    raise RuntimeError("CI: receiver start/stop/service commands forbidden")


control.service_action = deny
control.ReceiverController.start = deny
control.ReceiverController.stop = deny
control.ReceiverController.restart = deny
control.ReceiverController.close = lambda *_args, **_kwargs: None

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

application = QApplication([])
QSettings("Tihulu", "FlightRadar").setValue("auto_start_receiver", False)
QSettings("Tihulu", "FlightRadar").setValue("release_sdr_on_exit", False)
from tihulu_flight_radar.native import NativeRadarWindow

window = NativeRadarWindow()
try:
    if window.autostart_action.isChecked():
        raise AssertionError("Native CI window unexpectedly would auto-start receiver")
    if window.web.url().host() != "127.0.0.1":
        raise AssertionError("Native paired browser did not use private loopback")
    if not window.server_thread.is_alive():
        raise AssertionError("Ephemeral private bridge server is not alive")
    print("PASS: original frozen native Qt WebEngine window initialized at loopback.")
finally:
    window.close()
    application.processEvents()
    application.quit()

print("PASS: native Qt smoke window closed with receiver management disabled.")
