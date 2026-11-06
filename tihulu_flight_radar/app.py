"""Tihulu Flight Radar: accessible, cross-platform Qt desktop dashboard.

Retains every legacy v0.2 controller feature, adds live aircraft details.
All visible interface text is English; only observed aircraft data is shown.
"""
from __future__ import annotations

import json
from datetime import datetime
import platform
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QDialog,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from . import __version__
from .control import MODES, ReceiverController, service_action
from .core import (DataError, detect_sdr_processes, export_json, find_tar1090_url,
                   lan_ip, summarize, recently_seen, position_is_fresh)
from .map_server import LocalMapServer
from .tar_map import focused_tar_url


STYLE = """
QMainWindow { background: #11161e; }
QWidget#root { background: #11161e; color: #e9eef5; }
QScrollArea { border: none; background: #11161e; }
QFrame#card {
    background: #1c242f;
    border: 1px solid #344251;
    border-radius: 14px;
}
QFrame#metric {
    background: #202b37;
    border: 1px solid #3b4858;
    border-radius: 12px;
}
QLabel { background: transparent; color: #e9eef5; }
QLabel#eyebrow { color: #84a9bd; font-size: 11px; font-weight: 700; }
QLabel#pageTitle { color: #f4f7fa; font-size: 26px; font-weight: 750; }
QLabel#sectionTitle { color: #c6d2df; font-size: 12px; font-weight: 700; }
QLabel#muted { color: #9caec0; font-size: 12px; }
QLabel#statValue { color: #f5f8fa; font-size: 27px; font-weight: 750; }
QLabel#statLabel { color: #b8c6d3; font-size: 12px; }
QLabel#statusGood { color: #55d9aa; font-size: 14px; font-weight: 700; }
QLabel#statusWaiting { color: #f0c584; font-size: 14px; font-weight: 700; }
QLabel#statusOff { color: #b5c2d0; font-size: 14px; font-weight: 700; }
QLabel#statusError { color: #ff9b9b; font-size: 14px; font-weight: 700; }
QPushButton, QToolButton {
    background: #2b394a; color: #f4f7fa;
    border: 1px solid #445468; border-radius: 9px;
    padding: 9px 12px; font-weight: 600;
    min-height: 20px;
}
QPushButton:hover, QToolButton:hover { background: #3a4e63; }
QPushButton:disabled { color: #8192a3; background: #222d38; }
QPushButton#start { background: #227d67; border-color: #318c78; }
QPushButton#start:hover { background: #29977e; }
QPushButton#stop { background: #844451; border-color: #9c5563; }
QPushButton#stop:hover { background: #a05261; }
QPushButton#map { background: #315c75; border-color: #437994; }
QPushButton#map:hover { background: #3e7895; }
QComboBox, QLineEdit {
    background: #243140; color: #f2f6fa;
    border: 1px solid #4a5c6e; border-radius: 8px;
    padding: 8px; selection-background-color: #387f99;
}
QTableWidget {
    background: #1c242f; color: #e4ebf2;
    alternate-background-color: #222d39; gridline-color: #344251;
    border: 1px solid #3b4858; border-radius: 8px;
    selection-background-color: #285c74;
}
QHeaderView::section {
    background: #273442; color: #d6e3ed;
    padding: 9px 6px; border: none;
    border-bottom: 1px solid #465669; font-weight: 700;
}
QTableCornerButton::section { background: #273442; }
QCheckBox { color: #e0e8f0; spacing: 9px; }
"""


def text(value: str, kind: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(value)
    if kind:
        widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def add_card(parent: QVBoxLayout, title: str) -> QVBoxLayout:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 15, 16, 15)
    layout.setSpacing(11)
    layout.addWidget(text(title.upper(), "sectionTitle"))
    parent.addWidget(frame)
    return layout


def display(value, suffix="") -> str:
    """Format only the actual supplied field, without fabricating a value."""
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    return f"{value}{suffix}"


def flight_label(aircraft: dict) -> str:
    return str(aircraft.get("flight") or "").strip() or "—"


def aircraft_fields(aircraft: dict) -> list[str]:
    return [
        flight_label(aircraft),
        str(aircraft.get("hex") or "—"),
        str(aircraft.get("r") or "—"),
        str(aircraft.get("t") or "—"),
        display(aircraft.get("alt_baro", aircraft.get("alt_geom"))),
        display(aircraft.get("gs")),
        display(aircraft.get("track")),
        display(aircraft.get("seen"), "s"),
    ]


class RadarWindow(QMainWindow):
    def __init__(self, controller=None, owns_receiver=True):
        super().__init__()
        self.controller = controller if controller is not None else ReceiverController()
        self._owns_receiver = owns_receiver
        self._map_dialogs = []
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tihulu-radar")
        self.snapshot_future = None
        self.action_future = None
        self.map_future = None
        self._snapshot_generation = 0
        self._future_generation = 0
        self.last_data = None
        self.last_messages = None
        self.last_time = None
        self.aircraft_rows = []
        self._boot_updating = False
        self.map_server = LocalMapServer(lambda: self.last_data)
        self.map_server.start()
        self.settings = QSettings("Tihulu", "FlightRadar")
        self.setWindowTitle(f"Tihulu Flight Radar {__version__}")
        self.resize(900, 790)
        self.setMinimumSize(510, 550)
        self._build()
        self._load_config()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(2000)
        self._tick()

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root = QWidget()
        root.setObjectName("root")
        body = QVBoxLayout(root)
        body.setContentsMargins(21, 20, 21, 20)
        body.setSpacing(14)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

        body.addWidget(text("TIHULU   /   1090 MHz ADS-B + MODE S", "eyebrow"))
        body.addWidget(text("Flight Radar", "pageTitle"))
        body.addWidget(text("Live aircraft receiver  ·  Local-first  ·  Real observations only", "muted"))

        status = add_card(body, "Receiver status")
        self.state_label = text("Checking receiver…", "statusWaiting")
        status.addWidget(self.state_label)
        self.detail_label = text("Checking receiver source and decoder", "muted", True)
        status.addWidget(self.detail_label)

        controls = add_card(body, "Receiver control")
        row = QHBoxLayout()
        row.setSpacing(9)
        self.start_button = QPushButton("▶  Start")
        self.start_button.setObjectName("start")
        self.start_button.clicked.connect(lambda: self._action("start"))
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(lambda: self._action("stop"))
        self.restart_button = QPushButton("↻  Restart")
        self.restart_button.clicked.connect(lambda: self._action("restart"))
        for button in (self.start_button, self.stop_button, self.restart_button):
            row.addWidget(button)
        controls.addLayout(row)
        self.info = text(
            "Stopping releases the SDR for other applications (FM, DAB+ or RTL-433).",
            "muted", True
        )
        controls.addWidget(self.info)

        metrics = QGridLayout()
        metrics.setSpacing(10)
        self.metric_widgets = {}
        for index, (key, caption) in enumerate([
            ("aircraft", "Aircraft seen"),
            ("positioned", "With position"),
            ("rate", "Messages / second"),
            ("messages", "Total messages"),
        ]):
            frame = QFrame()
            frame.setObjectName("metric")
            tile = QVBoxLayout(frame)
            tile.setContentsMargins(14, 12, 14, 12)
            tile.setSpacing(3)
            value = text("—", "statValue")
            tile.addWidget(value)
            tile.addWidget(text(caption, "statLabel"))
            metrics.addWidget(frame, index // 2, index % 2)
            self.metric_widgets[key] = value
        stats_section = add_card(body, "Live reception")
        stats_section.addLayout(metrics)
        self.rssi = text("Average aircraft RSSI: —", "muted")
        stats_section.addWidget(self.rssi)

        map_section = add_card(body, "Map & exports")
        map_row = QHBoxLayout()
        self.map_button = QPushButton("↗  Open built-in aircraft map")
        self.map_button.setObjectName("map")
        self.map_button.clicked.connect(self._open_map)
        self.full_map_button = QPushButton("↗  Open full tar1090 map")
        self.full_map_button.clicked.connect(self._open_tar1090)
        map_row.addWidget(self.map_button)
        map_row.addWidget(self.full_map_button)
        map_section.addLayout(map_row)
        export_row = QHBoxLayout()
        self.export_button = QPushButton("↓  Export JSON as…")
        self.export_button.clicked.connect(self._export)
        self.quick_export_button = QPushButton("↓  Quick export (timestamped)")
        self.quick_export_button.clicked.connect(self._quick_export)
        export_row.addWidget(self.export_button)
        export_row.addWidget(self.quick_export_button)
        map_section.addLayout(export_row)
        map_section.addWidget(text(
            "Built-in map opens even without aircraft (Germany default). "
            "Full tar1090 map preserves the earlier detailed aircraft view when installed.",
            "muted", True
        ))
        self.lan_label = text("LAN tar1090 map: checking…", "muted")
        map_section.addWidget(self.lan_label)

        planes = add_card(body, "Aircraft currently received")
        self.aircraft_hint = text("Waiting for recent ADS-B / Mode S aircraft…", "muted", True)
        planes.addWidget(self.aircraft_hint)
        self.aircraft_table = QTableWidget(0, 8)
        self.aircraft_table.setHorizontalHeaderLabels([
            "Flight", "ICAO", "Reg.", "Type", "Altitude (ft)",
            "Speed (kt)", "Track (°)", "Seen",
        ])
        self.aircraft_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.aircraft_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.aircraft_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.aircraft_table.setAlternatingRowColors(True)
        self.aircraft_table.verticalHeader().setVisible(False)
        self.aircraft_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.aircraft_table.horizontalHeader().setStretchLastSection(True)
        self.aircraft_table.setMinimumHeight(170)
        self.aircraft_table.setMaximumHeight(260)
        self.aircraft_table.itemDoubleClicked.connect(self._show_aircraft_details)
        planes.addWidget(self.aircraft_table)
        aircraft_actions = QHBoxLayout()
        self.details_button = QPushButton("Aircraft details")
        self.details_button.clicked.connect(self._show_aircraft_details)
        self.follow_button = QPushButton("Show selected on map")
        self.follow_button.clicked.connect(self._focus_selected_map)
        aircraft_actions.addWidget(self.details_button)
        aircraft_actions.addWidget(self.follow_button)
        planes.addLayout(aircraft_actions)

        self.settings_toggle = QToolButton()
        self.settings_toggle.setText("▸  Receiver settings and startup options")
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.toggled.connect(self._toggle_settings)
        body.addWidget(self.settings_toggle)
        self.settings_frame = QFrame()
        self.settings_frame.setObjectName("card")
        settings = QVBoxLayout(self.settings_frame)
        settings.setContentsMargins(16, 16, 16, 16)
        settings.addWidget(text("INPUT SOURCE", "sectionTitle"))
        self.mode_select = QComboBox()
        self.mode_select.addItems(MODES)
        settings.addWidget(self.mode_select)
        settings.addWidget(text("Remote aircraft.json URL (remote mode only)", "muted"))
        self.remote_field = QLineEdit()
        self.remote_field.setPlaceholderText("http://receiver.lan/data/aircraft.json")
        settings.addWidget(self.remote_field)
        settings.addWidget(text("readsb executable (direct receiver mode only)", "muted"))
        self.decoder_field = QLineEdit()
        self.decoder_field.setPlaceholderText("Auto-detect from PATH")
        settings.addWidget(self.decoder_field)
        apply_button = QPushButton("Apply receiver configuration")
        apply_button.clicked.connect(self._apply_config)
        settings.addWidget(apply_button)
        self.boot_checkbox = QCheckBox("Start readsb / tar1090 at system boot")
        self.boot_checkbox.setVisible(platform.system() == "Linux")
        self.boot_checkbox.toggled.connect(self._toggle_boot)
        settings.addWidget(self.boot_checkbox)
        self.release_checkbox = QCheckBox("Release local SDR when app closes")
        self.release_checkbox.setChecked(
            self.settings.value("release_sdr_on_exit", True, type=bool)
        )
        self.release_checkbox.toggled.connect(
            lambda value: self.settings.setValue("release_sdr_on_exit", value)
        )
        settings.addWidget(self.release_checkbox)
        self.diagnostics_button = QPushButton("View receiver diagnostics")
        self.diagnostics_button.setVisible(platform.system() == "Linux")
        self.diagnostics_button.clicked.connect(self._show_diagnostics)
        settings.addWidget(self.diagnostics_button)
        settings.addWidget(text(
            "Existing systemd services remain active when this window closes. "
            "A decoder launched in Direct readsb mode stops with the application.",
            "muted", True
        ))
        body.addWidget(self.settings_frame)
        self.settings_frame.setVisible(False)

    def _toggle_settings(self, visible: bool):
        self.settings_frame.setVisible(visible)
        self.settings_toggle.setText(
            "▾  Receiver settings and startup options" if visible
            else "▸  Receiver settings and startup options"
        )

    def _load_config(self):
        mode = str(self.settings.value("mode", self.controller.mode))
        remote = str(self.settings.value("remote", ""))
        # Previous versions allowed persisting Remote JSON with no URL.
        # Recover a useful default on Linux without losing valid saved setups.
        if mode == "Remote JSON" and not remote.strip():
            mode = "Linux services" if platform.system() == "Linux" else "Direct readsb"
        self.mode_select.setCurrentText(mode if mode in MODES else self.controller.mode)
        self.remote_field.setText(remote)
        self.decoder_field.setText(str(self.settings.value("decoder", "")))
        self._apply_config(quiet=True)
        if platform.system() == "Linux":
            address = lan_ip()
            self.lan_label.setText(
                f"LAN tar1090 map: http://{address}/tar1090/"
                if address else "LAN tar1090 URL unavailable — use local map"
            )
            self._boot_updating = True
            try:
                states = []
                for unit in ("readsb.service", "tar1090.service"):
                    result = subprocess.run(
                        ["/usr/bin/systemctl", "is-enabled", unit],
                        capture_output=True, text=True, timeout=3, check=False
                    )
                    states.append(result.returncode == 0 and result.stdout.strip() == "enabled")
                self.boot_checkbox.setChecked(all(states))
                if any(states) and not all(states):
                    self.info.setText(
                        "Startup configuration is mixed: readsb and tar1090 "
                        "have different boot settings. Toggle to synchronize."
                    )
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                self._boot_updating = False

    def _apply_config(self, quiet=False):
        if self.action_future is not None:
            if not quiet:
                QMessageBox.information(self, "Receiver busy",
                                        "Wait for the current operation to finish.")
            return
        mode = self.mode_select.currentText()
        remote = self.remote_field.text().strip()
        if mode == "Remote JSON" and not remote:
            if not quiet:
                QMessageBox.warning(self, "Missing receiver URL",
                                    "Enter a valid http:// or https:// aircraft.json URL.")
            return
        try:
            self.controller.configure(mode, remote, self.decoder_field.text())
            self.settings.setValue("mode", self.controller.mode)
            self.settings.setValue("remote", self.controller.remote_url)
            self.settings.setValue("decoder", self.controller.decoder_path)
            self._invalidate_snapshot()
            if not quiet:
                self.info.setText("Receiver configuration applied.")
        except DataError as exc:
            if not quiet:
                QMessageBox.warning(self, "Receiver configuration", str(exc))

    def _invalidate_snapshot(self):
        self._snapshot_generation += 1
        self.last_data = None
        self.last_messages = None
        self.last_time = None
        self.aircraft_rows = []
        self.aircraft_table.setRowCount(0)
        self.aircraft_hint.setText("Waiting for current receiver data…")
        for field in self.metric_widgets.values():
            field.setText("—")
        self.rssi.setText("Average aircraft RSSI: —")

    def _action(self, operation: str):
        if self.action_future is not None:
            return
        self._invalidate_snapshot()
        self.info.setText(f"{operation.capitalize()} receiver requested…")
        methods = {
            "start": self.controller.start,
            "stop": self.controller.stop,
            "restart": self.controller.restart,
        }
        self.action_future = self.pool.submit(methods[operation])

    def _toggle_boot(self, enabled: bool):
        if self._boot_updating or platform.system() != "Linux":
            return
        if self.action_future is not None:
            self._boot_updating = True
            self.boot_checkbox.setChecked(not enabled)
            self._boot_updating = False
            return
        self.action_future = self.pool.submit(
            service_action, "enable" if enabled else "disable"
        )
        self.info.setText("Updating system startup preference…")

    def _tick(self):
        if self.map_future is not None and self.map_future.done():
            try:
                url = self.map_future.result()
                if url:
                    target = focused_tar_url(url, self.last_data)
                    self._show_embedded_map(target, "Full tar1090 aircraft map")
                    self.info.setText("Full tar1090 focused on recent aircraft or Germany.")
                else:
                    QMessageBox.information(
                        self, "Full map unavailable",
                        "tar1090 is not reachable. Open the built-in map instead, "
                        "or check the tar1090/lighttpd services."
                    )
            except Exception as exc:
                self.info.setText(f"Map discovery failed: {exc}")
            finally:
                self.map_future = None

        if self.action_future is not None and self.action_future.done():
            try:
                self.info.setText(str(self.action_future.result()))
            except Exception as exc:
                self.info.setText(f"Operation failed: {exc}")
                QMessageBox.warning(self, "Receiver operation failed", str(exc))
            finally:
                self._invalidate_snapshot()
                self.action_future = None

        busy = self.action_future is not None
        mode = self.controller.mode
        active, detail = self.controller.status()
        if mode == "Remote JSON":
            self.state_label.setText("●  REMOTE RECEIVER")
            self.state_label.setObjectName("statusWaiting")
        elif busy:
            self.state_label.setText("●  RECEIVER OPERATION IN PROGRESS")
            self.state_label.setObjectName("statusWaiting")
        elif active:
            self.state_label.setText("●  DECODER ACTIVE — WAITING FOR MESSAGES")
            self.state_label.setObjectName("statusWaiting")
        else:
            self.state_label.setText("●  RECEIVER STOPPED")
            self.state_label.setObjectName("statusOff")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)
        self.detail_label.setText(detail)
        self.start_button.setEnabled(not busy and not active and mode != "Remote JSON")
        self.stop_button.setEnabled(not busy and active and mode != "Remote JSON")
        self.restart_button.setEnabled(not busy and active and mode != "Remote JSON")
        self.boot_checkbox.setEnabled(not busy and mode == "Linux services")
        self.mode_select.setEnabled(not busy)
        self.diagnostics_button.setEnabled(not busy)

        if busy or (mode != "Remote JSON" and not active):
            return
        if self.snapshot_future is None:
            self._future_generation = self._snapshot_generation
            self.snapshot_future = self.pool.submit(self.controller.snapshot)
        elif self.snapshot_future.done():
            try:
                result = self.snapshot_future.result()
                if self._future_generation != self._snapshot_generation:
                    return
                self.last_data = result
                summary = summarize(result)
                now = time.monotonic()
                total = summary["messages"]
                rate = 0.0
                if (self.last_time is not None and self.last_messages is not None
                        and total >= self.last_messages):
                    rate = (total - self.last_messages) / max(now - self.last_time, .01)
                self.last_messages, self.last_time = total, now
                for key in ("aircraft", "positioned", "messages"):
                    self.metric_widgets[key].setText(f"{summary[key]:,}")
                self.metric_widgets["rate"].setText(f"{rate:.1f}")
                signal = summary["mean_rssi"]
                self.rssi.setText(
                    "Average aircraft RSSI: —" if signal is None
                    else f"Average aircraft RSSI: {signal:.1f} dBFS"
                )
                self._update_aircraft(result.get("aircraft", []))
                if total > 0 and rate > 0:
                    self.state_label.setText("●  RECEIVING ADS-B / MODE S")
                    self.state_label.setObjectName("statusGood")
                elif mode == "Remote JSON":
                    self.state_label.setText("●  REMOTE DATA CONNECTED")
                    self.state_label.setObjectName("statusGood")
                else:
                    self.state_label.setText("●  DECODER ACTIVE — NO RECENT MESSAGES")
                    self.state_label.setObjectName("statusWaiting")
                self.state_label.style().unpolish(self.state_label)
                self.state_label.style().polish(self.state_label)
                self.detail_label.setText(
                    detail + (" · Aircraft data updating." if total > 0
                              else " · No RF messages yet. Check antenna/SDR ownership.")
                )
            except Exception as exc:
                if self._future_generation == self._snapshot_generation:
                    self.last_data = None
                    self.last_messages = None
                    self.last_time = None
                    self.aircraft_rows = []
                    self.aircraft_table.setRowCount(0)
                    self.aircraft_hint.setText("No fresh receiver data. " + str(exc)[:100])
                    for field in self.metric_widgets.values():
                        field.setText("—")
                    self.rssi.setText("Average aircraft RSSI: —")
                    self.detail_label.setText(str(exc)[:180])
            finally:
                self.snapshot_future = None

    def _update_aircraft(self, records):
        recent = [
            aircraft for aircraft in records
            if isinstance(aircraft, dict) and recently_seen(aircraft)
        ]
        recent.sort(key=lambda a: a.get("seen", 999))
        self.aircraft_rows = recent[:200]
        # Preserve selection when subsequent snapshots update rows.
        old_index = self.aircraft_table.currentRow()
        selected_icao = None
        if 0 <= old_index < self.aircraft_table.rowCount():
            cell = self.aircraft_table.item(old_index, 1)
            selected_icao = cell.text() if cell else None
        self.aircraft_table.setRowCount(len(self.aircraft_rows))
        reselect = -1
        for i, aircraft in enumerate(self.aircraft_rows):
            for j, value in enumerate(aircraft_fields(aircraft)):
                self.aircraft_table.setItem(i, j, QTableWidgetItem(value))
            if aircraft.get("hex") and str(aircraft["hex"]) == selected_icao:
                reselect = i
        if reselect >= 0:
            self.aircraft_table.selectRow(reselect)
        self.aircraft_hint.setText(
            f"{len(recent)} aircraft received in the last 60 seconds · "
            f"{sum(isinstance(a.get('lat'), (int, float)) and isinstance(a.get('lon'), (int, float)) and isinstance(a.get('seen_pos'), (int, float)) and a['seen_pos'] <= 60 for a in recent)} with recent coordinates"
        )

    def _selected_aircraft(self) -> dict | None:
        index = self.aircraft_table.currentRow()
        if index < 0 or index >= len(self.aircraft_rows):
            QMessageBox.information(self, "Select an aircraft",
                                    "Choose a received aircraft from the list first.")
            return None
        return self.aircraft_rows[index]

    def _show_aircraft_details(self, *_):
        aircraft = self._selected_aircraft()
        if aircraft is None:
            return
        position = (
            f"{aircraft['lat']:.5f}, {aircraft['lon']:.5f}"
            if isinstance(aircraft.get("lat"), (int, float))
            and isinstance(aircraft.get("lon"), (int, float))
            else "Not broadcast / unavailable"
        )
        fields = [
            ("Callsign", flight_label(aircraft)),
            ("ICAO / aircraft address", aircraft.get("hex")),
            ("Registration", aircraft.get("r")),
            ("Aircraft type", aircraft.get("t")),
            ("Position", position),
            ("Position age", display(aircraft.get("seen_pos"), "s")),
            ("Barometric altitude", display(aircraft.get("alt_baro"), " ft")),
            ("Geometric altitude", display(aircraft.get("alt_geom"), " ft")),
            ("Ground speed", display(aircraft.get("gs"), " kt")),
            ("Track", display(aircraft.get("track"), "°")),
            ("Vertical speed", display(aircraft.get("baro_rate"), " ft/min")),
            ("RSSI", display(aircraft.get("rssi"), " dBFS")),
            ("Last seen", display(aircraft.get("seen"), "s")),
            ("Message count", display(aircraft.get("messages"))),
            ("Data type", aircraft.get("type")),
        ]
        body = "\n".join(f"{key}: {display(value)}" for key, value in fields)
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Aircraft information")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(body)
        dialog.setDetailedText(json.dumps(aircraft, indent=2, ensure_ascii=False))
        dialog.exec()

    def _show_embedded_map(self, url: str, title: str):
        """Render the radar inside the Qt application, not a system browser."""
        from PySide6.QtWebEngineWidgets import QWebEngineView
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowTitle(title)
        dialog.resize(1170, 800)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        view = QWebEngineView(dialog)
        layout.addWidget(view)
        view.setUrl(QUrl(url))
        self._map_dialogs.append(dialog)
        dialog.destroyed.connect(
            lambda *_: self._map_dialogs.remove(dialog)
            if dialog in self._map_dialogs else None
        )
        dialog.show()

    def _open_map(self):
        self._show_embedded_map(self.map_server.url, "Built-in ADS-B aircraft map")

    def _open_tar1090(self):
        if self.map_future is None:
            self.info.setText("Checking for the full local tar1090 map…")
            self.map_future = self.pool.submit(find_tar1090_url)

    def _focus_selected_map(self):
        aircraft = self._selected_aircraft()
        if aircraft is None:
            return
        if not position_is_fresh(aircraft):
            QMessageBox.information(
                self, "Aircraft position unavailable",
                "This aircraft has no fresh ADS-B coordinates. "
                "Its identity and other received information remain in the list, "
                "but it cannot be positioned on the map."
            )
            return
        icao = str(aircraft.get("hex") or "")
        if not icao:
            self._open_map()
            return
        self._show_embedded_map(
            self.map_server.url + "?aircraft=" + quote(icao, safe=""),
            "Selected ADS-B aircraft map",
        )

    def _show_diagnostics(self):
        if platform.system() != "Linux":
            return
        reports = []
        for heading, command in (
            ("readsb status", ["/usr/bin/systemctl", "status", "readsb.service",
                              "--no-pager", "--lines=10"]),
            ("readsb logs", ["journalctl", "-u", "readsb.service",
                             "-n", "15", "--no-pager"]),
        ):
            try:
                r = subprocess.run(command, capture_output=True, text=True,
                                   check=False, timeout=4)
                reports.append(f"{heading}:\n{(r.stdout or r.stderr or 'No information')[-1800:]}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                reports.append(f"{heading}: {exc}")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Receiver diagnostics")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText("\n\n".join(reports))
        dialog.exec()

    def _quick_export(self):
        if self.last_data is None:
            QMessageBox.information(
                self, "No live data", "No fresh aircraft.json snapshot is available."
            )
            return
        directory = Path.home() / "Downloads"
        if not directory.is_dir():
            directory = Path.home()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = directory / f"tihulu-adsb-{stamp}.json"
        counter = 1
        while path.exists():
            path = directory / f"tihulu-adsb-{stamp}-{counter}.json"
            counter += 1
        try:
            export_json(self.last_data, path)
            self.info.setText(f"Saved received aircraft data: {path}")
        except (OSError, DataError) as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _export(self):
        if self.last_data is None:
            QMessageBox.information(self, "No live data",
                                    "No fresh aircraft.json snapshot is available.")
            return
        name, _ = QFileDialog.getSaveFileName(
            self, "Export aircraft JSON",
            str(Path.home() / "Downloads" / "tihulu-aircraft.json"),
            "JSON Files (*.json)"
        )
        if name:
            try:
                export_json(self.last_data, Path(name))
                self.info.setText("Saved real aircraft snapshot: " + name)
            except (OSError, DataError) as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def closeEvent(self, event):
        self.timer.stop()
        for dialog in list(self._map_dialogs):
            dialog.close()
        self.map_server.close()
        if self._owns_receiver:
            try:
                self.controller.close(
                    release_local_service=self.release_checkbox.isChecked()
                )
            except DataError as exc:
                QMessageBox.warning(self, "Receiver release warning", str(exc))
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Tihulu Flight Radar")
    application.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#11161e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e9eef5"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1c242f"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#222d39"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e9eef5"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2b394a"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f4f7fa"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2b7290"))
    application.setPalette(palette)
    application.setStyleSheet(STYLE)
    window = RadarWindow()
    window.show()
    return application.exec()
