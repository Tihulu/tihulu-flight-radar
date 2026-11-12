#!/usr/bin/env python3
"""CI-only classic Qt smoke with forced receiver/service-disable safeguards.

This wraps the original smoke without modifying original 0.3.2.dev4 sources.
Runs in an ephemeral HOME with no SDR device and no shared systemd service access.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path

if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    raise RuntimeError("Only offscreen CI Qt smoke is allowed")
if not os.environ.get("CI") or not os.environ.get("GITHUB_ACTIONS"):
    raise RuntimeError("Not intended to run on the owner's workstation")
if not os.environ.get("RUNNER_TEMP"):
    raise RuntimeError("Disposable runner environment required")
if os.environ.get("HOME") != os.environ.get("RUNNER_TEMP") + "/installed-snapshot-home":
    raise RuntimeError("HOME must point to the isolated temporary CI profile")

import tihulu_flight_radar.control as control


def deny(*_args, **_kwargs):
    raise RuntimeError("CI REPLAY: active receiver operations prohibited")


# Patch BEFORE importing original app.py, because app.py may capture imported names.
control.service_action = deny
control.ReceiverController.start = deny
control.ReceiverController.stop = deny
control.ReceiverController.restart = deny
control.ReceiverController.close = lambda *_args, **_kwargs: None

source = Path(__file__).resolve().parents[1] / "source" / "scripts" / "qt_smoke.py"
runpy.run_path(str(source), run_name="__main__")
print("PASS: guarded classic Qt smoke ran without active receiver control.")
