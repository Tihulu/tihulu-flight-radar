"""Portable Qt desktop UI. All user-facing text is English."""
from __future__ import annotations

import platform
import subprocess
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from . import __version__
from .control import MODES, ReceiverController, service_action
from .core import DataError, export_json, summarize
from .map_server import LocalMapServer


STYLES = """
QWidget { background: #10131a; color: #f2f4f8; font-size: 13px; }
QFrame#panel { background: #191f29; border: 1px solid #303845; border-radius: 12px; }
QLabel#title { font-size: 25px; font-weight: 700; }
QLabel#heading { color: #96aec0; font-size: 12px; font-weight: 700; }
QLabel#metric { font-size: 28px; font-weight: 700; }
QLabel#muted { color: #a8b1bf; }
QPushButton { background: #2b3442; border: 1px solid #3d495b; border-radius: 8px;
              padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #364253; }
QPushButton:disabled { color: #687483; background: #202632; }
QPushButton#start { background: #247e69; color: white; }
QPushButton#stop { background: #8c424c; color: white; }
QLineEdit, QComboBox { background: #202837; border: 1px solid #3d485b;
                     padding: 8px; border-radius: 8px; }
QScrollArea { border: none; }
"""


def label(message: str, kind: str = "", wrap: bool = False) -> QLabel:
    item = QLabel(message)
    if kind:
        item.setObjectName(kind)
    item.setWordWrap(wrap)
    return item


def panel(parent: QVBoxLayout, title: str) -> QVBoxLayout:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(17, 15, 17, 15)
    layout.setSpacing(10)
    layout.addWidget(label(title.upper(), "heading"))
    parent.addWidget(frame)
    return layout


class RadarWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = ReceiverController()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="radar")
        self.snapshot_future = None
        self.action_future = None
        self.last_data = None
        self.last_messages = None
        self.last_time = None
        self._boot_updating = False
        self.map_server = LocalMapServer(lambda: self.last_data)
        self.map_server.start()
        self.settings = QSettings("Tihulu", "FlightRadar")
        self.setWindowTitle(f"Tihulu Flight Radar {__version__}")
        self.resize(850, 750)
        self.setMinimumSize(480, 560)
        self._make_ui()
        self._load_config()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(2000)
        self._tick()

    def _make_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root = QWidget()
        self.layout = QVBoxLayout(root)
        self.layout.setContentsMargins(22, 22, 22, 22)
        self.layout.setSpacing(15)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        self.layout.addWidget(label("TIHULU  /  FLIGHT RADAR", "heading"))
        self.layout.addWidget(label("Live ADS-B & Mode S", "title"))
        self.layout.addWidget(label("1090 MHz  ·  Local-first  ·  Real receiver data only", "muted"))
        state = panel(self.layout, "Receiver status")
        self.state_label = label("Checking receiver…")
        state.addWidget(self.state_label)
        self.detail_label = label("Waiting for aircraft.json", "muted", True)
        state.addWidget(self.detail_label)
        control = panel(self.layout, "Receiver controls")
        control_row = QHBoxLayout()
        self.start_button = QPushButton("▶  Start receiver")
        self.start_button.setObjectName("start")
        self.start_button.clicked.connect(lambda: self._action("start"))
        self.stop_button = QPushButton("■  Stop receiver")
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(lambda: self._action("stop"))
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control.addLayout(control_row)
        self.info = label("Select an input mode below. One SDR can serve only one decoder at a time.", "muted", True)
        control.addWidget(self.info)
        metrics = panel(self.layout, "Live reception")
        metric_grid = QGridLayout()
        self.metric_widgets = {}
        for index, (key, title) in enumerate([
            ("aircraft", "Aircraft seen"),
            ("positioned", "With position"),
            ("rate", "Messages / second"),
            ("messages", "Total messages"),
        ]):
            tile = QFrame()
            tile.setObjectName("panel")
            tile_layout = QVBoxLayout(tile)
            value = label("—", "metric")
            tile_layout.addWidget(value)
            tile_layout.addWidget(label(title, "muted"))
            metric_grid.addWidget(tile, index // 2, index % 2)
            self.metric_widgets[key] = value
        metrics.addLayout(metric_grid)
        self.rssi = label("Average aircraft RSSI: —", "muted")
        metrics.addWidget(self.rssi)
        map_section = panel(self.layout, "Map & data")
        actions = QHBoxLayout()
        self.map_button = QPushButton("Open live map")
        self.map_button.clicked.connect(lambda: webbrowser.open(self.map_server.url))
        self.export_button = QPushButton("Export JSON")
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.map_button)
        actions.addWidget(self.export_button)
        map_section.addLayout(actions)
        map_section.addWidget(label("Offline coordinate map; optional OpenStreetMap tiles when online.", "muted", True))
        sources = panel(self.layout, "Receiver configuration")
        sources.addWidget(label("Input mode", "muted"))
        self.mode_select = QComboBox()
        self.mode_select.addItems(MODES)
        sources.addWidget(self.mode_select)
        sources.addWidget(label("Remote aircraft.json URL (for Remote JSON mode)", "muted"))
        self.remote_field = QLineEdit()
        self.remote_field.setPlaceholderText("http://192.168.1.10/tar1090/data/aircraft.json")
        sources.addWidget(self.remote_field)
        sources.addWidget(label("readsb executable (optional, for Direct readsb mode)", "muted"))
        self.decoder_field = QLineEdit()
        self.decoder_field.setPlaceholderText("Auto-detect from PATH")
        sources.addWidget(self.decoder_field)
        save_button = QPushButton("Apply receiver configuration")
        save_button.clicked.connect(self._apply_config)
        sources.addWidget(save_button)
        self.boot_checkbox = QCheckBox("Start Linux services at system boot")
        self.boot_checkbox.setVisible(platform.system() == "Linux")
        self.boot_checkbox.toggled.connect(self._toggle_boot)
        sources.addWidget(self.boot_checkbox)
        self.layout.addWidget(label("Closing the app stops only a directly launched decoder. Existing system services continue until stopped.", "muted", True))

    def _load_config(self):
        mode = str(self.settings.value("mode", self.controller.mode))
        self.mode_select.setCurrentText(mode if mode in MODES else self.controller.mode)
        self.remote_field.setText(str(self.settings.value("remote", "")))
        self.decoder_field.setText(str(self.settings.value("decoder", "")))
        self._apply_config(quiet=True)
        if platform.system() == "Linux":
            self._boot_updating = True
            try:
                r = subprocess.run(["/usr/bin/systemctl", "is-enabled", "readsb.service"],
                                   capture_output=True, text=True, timeout=3, check=False)
                self.boot_checkbox.setChecked(r.returncode == 0 and r.stdout.strip() == "enabled")
            except (OSError, subprocess.TimeoutExpired):
                pass
            self._boot_updating = False

    def _apply_config(self, quiet=False):
        try:
            self.controller.configure(self.mode_select.currentText(),
                                      self.remote_field.text(),
                                      self.decoder_field.text())
            self.settings.setValue("mode", self.controller.mode)
            self.settings.setValue("remote", self.controller.remote_url)
            self.settings.setValue("decoder", self.controller.decoder_path)
            self.last_data = None
            self.last_messages = None
            self.last_time = None
            if not quiet:
                self.info.setText("Receiver configuration applied.")
        except DataError as exc:
            if not quiet:
                QMessageBox.warning(self, "Receiver configuration", str(exc))

    def _action(self, operation: str):
        if self.action_future is not None:
            return
        self.info.setText("Applying receiver operation…")
        method = self.controller.start if operation == "start" else self.controller.stop
        self.action_future = self.pool.submit(method)

    def _toggle_boot(self, enabled: bool):
        if self._boot_updating or platform.system() != "Linux":
            return
        if self.action_future is not None:
            return
        self.action_future = self.pool.submit(service_action, "enable" if enabled else "disable")
        self.info.setText("Updating system boot preference…")

    def _tick(self):
        if self.action_future is not None and self.action_future.done():
            try:
                self.info.setText(str(self.action_future.result()))
            except Exception as exc:
                self.info.setText(f"Operation failed: {exc}")
                QMessageBox.warning(self, "Receiver operation failed", str(exc))
            self.action_future = None
        busy = self.action_future is not None
        mode = self.controller.mode
        active, detail = self.controller.status()
        self.state_label.setText("●  RECEIVER RUNNING" if active else
                                 "●  REMOTE MONITOR" if mode == "Remote JSON" else
                                 "●  RECEIVER STOPPED")
        self.detail_label.setText(detail)
        self.start_button.setEnabled(not busy and not active and mode != "Remote JSON")
        self.stop_button.setEnabled(not busy and active and mode != "Remote JSON")
        self.boot_checkbox.setEnabled(not busy and mode == "Linux services")
        if self.snapshot_future is None:
            self.snapshot_future = self.pool.submit(self.controller.snapshot)
        elif self.snapshot_future.done():
            try:
                data = self.snapshot_future.result()
                self.last_data = data
                summary = summarize(data)
                now = time.monotonic()
                total = summary["messages"]
                rate = 0.0
                if self.last_time is not None and self.last_messages is not None and total >= self.last_messages:
                    rate = (total - self.last_messages) / max(now - self.last_time, 0.01)
                self.last_time, self.last_messages = now, total
                for key in ("aircraft", "positioned", "messages"):
                    self.metric_widgets[key].setText(f"{summary[key]:,}")
                self.metric_widgets["rate"].setText(f"{rate:.1f}")
                signal = summary["mean_rssi"]
                self.rssi.setText("Average aircraft RSSI: —" if signal is None
                                  else f"Average aircraft RSSI: {signal:.1f} dBFS")
                self.detail_label.setText(detail + "  ·  Real aircraft.json received.")
            except Exception as exc:
                self.last_data = None
                self.last_time = None
                self.last_messages = None
                for metric in self.metric_widgets.values():
                    metric.setText("—")
                self.rssi.setText("Average aircraft RSSI: —")
                self.detail_label.setText(str(exc)[:180])
            finally:
                self.snapshot_future = None

    def _export(self):
        if self.last_data is None:
            QMessageBox.information(self, "No live data", "No fresh aircraft.json data is available to export.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export real ADS-B snapshot",
            str(Path.home() / "Downloads" / "tihulu-aircraft.json"),
            "JSON Files (*.json)")
        if filename:
            try:
                export_json(self.last_data, Path(filename))
                self.info.setText(f"Exported received data: {filename}")
            except (OSError, DataError) as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def closeEvent(self, event):
        self.timer.stop()
        self.map_server.close()
        self.controller.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Tihulu Flight Radar")
    application.setStyleSheet(STYLES)
    window = RadarWindow()
    window.show()
    return application.exec()
