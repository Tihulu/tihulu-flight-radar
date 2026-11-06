"""Tihulu Flight Radar — real in-application radar window.

The Qt WebEngine window renders the same map as GitHub Pages, but serves it
from a private local bridge and pairs automatically. It never launches the
system web browser or puts a bridge secret in a URL or persistent storage.
"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import Qt, QUrl, QSettings, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QVBoxLayout

from .bridge import Bridge, make_handler


class EmbeddedRadarView(QWebEngineView):
    """New-window requests (e.g. tar1090) become Qt dialogs, not browsers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popups: list[QDialog] = []

    def createWindow(self, _type):
        dialog = QDialog(self.window())
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowTitle("Tihulu Flight Radar — Additional map")
        dialog.resize(1180, 800)
        layout = QVBoxLayout(dialog)
        from .tar_overlay import TarOverlayView
        owner = self.window()
        provider = getattr(getattr(owner, "bridge", None), "online", None)
        child = TarOverlayView(dialog, provider=provider, assume_tar=True)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)
        self._popups.append(dialog)
        dialog.destroyed.connect(lambda *_: self._forget_popup(dialog))
        dialog.show()
        return child

    def _forget_popup(self, dialog):
        try:
            self._popups.remove(dialog)
        except ValueError:
            pass


class NativeRadarWindow(QMainWindow):
    """Dedicated native desktop GUI, automatically paired with its own bridge."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tihulu Flight Radar — Live Radar")
        self.resize(1420, 880)
        self.setMinimumSize(850, 560)
        self.settings = QSettings("Tihulu", "FlightRadar")
        self.bridge = Bridge(allow_control=True)
        # Share the user's already-configured receiver mode from the classic
        # dashboard. Earlier versions ignored this and defaulted to systemd,
        # hiding a working Direct readsb / Remote JSON receiver.
        from .control import MODES
        preferred = str(self.settings.value("mode", self.bridge.receiver.mode))
        remote = str(self.settings.value("remote", ""))
        decoder = str(self.settings.value("decoder", ""))
        if preferred == "Remote JSON" and not remote.strip():
            preferred = self.bridge.receiver.mode
        try:
            if preferred in MODES:
                self.bridge.receiver.configure(preferred, remote, decoder)
        except Exception:
            # An invalid saved URL must not crash the radar window.
            self.bridge.receiver.configure(self.bridge.receiver.mode)

        # Ephemeral loopback port allows multiple instances without taking over
        # an unrelated running service or requiring manual bridge connection.
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        self.server.RequestHandlerClass = make_handler(self.bridge, self.server.server_port)
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.2},
            name="tihulu-native-radar", daemon=True,
        )
        self.server_thread.start()
        self.local_url = f"http://127.0.0.1:{self.server.server_port}"

        self.web = EmbeddedRadarView(self)
        self.setCentralWidget(self.web)
        self.web.loadFinished.connect(self._paired_on_loaded)
        self.web.setUrl(QUrl(self.local_url + "/"))

        self.classic_window = None
        self._startup_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tihulu-rf-start")
        self._startup_future = None
        self._exit_requested = False
        self._startup_timer = QTimer(self)
        self._startup_timer.setInterval(250)
        self._startup_timer.timeout.connect(self._check_startup)
        menu = self.menuBar().addMenu("Receiver")
        classic = QAction("Open full classic receiver dashboard", self)
        classic.triggered.connect(self.open_classic)
        menu.addAction(classic)
        self.autostart_action = QAction("Start local receiver on application launch", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(
            self.settings.value("auto_start_receiver", True, type=bool)
        )
        self.autostart_action.toggled.connect(
            lambda checked: self.settings.setValue("auto_start_receiver", checked)
        )
        menu.addAction(self.autostart_action)
        self.release_action = QAction("Release local SDR on exit", self)
        self.release_action.setCheckable(True)
        self.release_action.setChecked(
            self.settings.value("release_sdr_on_exit", True, type=bool)
        )
        self.release_action.toggled.connect(
            lambda value: self.settings.setValue("release_sdr_on_exit", value)
        )
        menu.addAction(self.release_action)
        reload_view = QAction("Reload radar view", self)
        reload_view.triggered.connect(self.web.reload)
        menu.addAction(reload_view)
        about = QAction("About sources and permissions", self)
        about.triggered.connect(self._about)
        menu.addAction(about)
        self.statusBar().showMessage(
            "Local radar in this window · readsb reception separate from Internet data"
        )
        # Start after the GUI is visible; never auto-start remote receivers.
        # The startup is asynchronous so failing sudo/USB detection cannot
        # freeze the entire map or prevent Internet aircraft rendering.
        QTimer.singleShot(700, self._start_receiver_if_needed)

    def _start_receiver_if_needed(self):
        if (self._exit_requested or not self.autostart_action.isChecked()):
            return
        if self.bridge.receiver.mode == "Remote JSON":
            return
        self.bridge.last_start_error = None
        self.statusBar().showMessage("Checking local receiver and USB ownership…")
        self._startup_future = self._startup_pool.submit(self._ensure_receiver_active)
        self._startup_timer.start()

    def _ensure_receiver_active(self):
        with self.bridge.receiver_lock:
            active, message = self.bridge.receiver.status()
            if active:
                return "Local decoder already running: " + message
            return self.bridge.receiver.start()

    def _check_startup(self):
        f = self._startup_future
        if f is None or not f.done():
            return
        self._startup_timer.stop()
        self._startup_future = None
        try:
            result = f.result()
            self.bridge.last_start_error = None
            self.statusBar().showMessage(result)
        except Exception as exc:
            message = str(exc)
            self.bridge.last_start_error = message
            self.statusBar().showMessage("Local receiver unavailable: " + message)
        if not self._exit_requested:
            self.web.page().runJavaScript(
                "if (typeof checkReceiver === 'function') checkReceiver().catch(()=>{});"
            )
        else:
            # The close request waits for startup completion. Do not race a
            # systemd start and leave the USB device claimed after close.
            self.close()

    def _paired_on_loaded(self, ok: bool):
        if not ok:
            self.statusBar().showMessage("Local radar page failed to load; check Qt WebEngine.")
            return
        # Called only for this on-loopback document. The secret remains
        # ephemeral and is never copied into a browser URL or query string.
        if not (self.web.url().scheme() == "http"
                and self.web.url().host() == "127.0.0.1"
                and self.web.url().port() == self.server.server_port):
            self.statusBar().showMessage("Untrusted web origin — auto-pairing refused.")
            return
        code = (
            "if (typeof window.tihuluNativeConnect === 'function') { "
            "window.tihuluNativeConnect(" + json.dumps(self.local_url) + ", "
            + json.dumps(self.bridge.token) + "); }"
        )
        self.web.page().runJavaScript(code)

    def open_classic(self):
        # Native QWidget, not an external browser. The shared controller avoids
        # two independent readsb processes simultaneously owning one RTL-SDR.
        from .app import RadarWindow
        if self.classic_window is None:
            self.classic_window = RadarWindow(
                controller=self.bridge.receiver, owns_receiver=False
            )
            self.classic_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.classic_window.destroyed.connect(self._classic_closed)
        self.classic_window.show()
        self.classic_window.raise_()
        self.classic_window.activateWindow()

    def _classic_closed(self, *_):
        self.classic_window = None

    def _about(self):
        QMessageBox.information(
            self, "Tihulu Flight Radar",
            "The embedded window connects to a private 127.0.0.1 bridge automatically.\n"
            "Antenna data comes from an installed readsb receiver, if available.\n"
            "Internet data comes from adsb.lol; map center queries leave your device.\n"
            "No aircraft are simulated. No system browser is required.\n"
            "Receiver start/stop requires an explicit click and confirmation."
        )

    def closeEvent(self, event):
        if self._startup_future is not None and not self._startup_future.done():
            self._exit_requested = True
            self.statusBar().showMessage("Finishing receiver startup before safe shutdown…")
            event.ignore()
            return
        self._startup_timer.stop()
        self._startup_pool.shutdown(wait=False, cancel_futures=True)
        # Stop the app-owned direct child; optionally stop local readsb and
        # tar1090 services to release the same USB tuner for other SDR apps.
        if self.classic_window is not None:
            self.classic_window.close()
        self.web.setUrl(QUrl("about:blank"))
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        try:
            self.bridge.receiver.close(
                release_local_service=self.release_action.isChecked()
            )
        except Exception as exc:
            QMessageBox.warning(self, "Receiver release warning",
                                "The receiver may still be occupied: " + str(exc))
        super().closeEvent(event)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Tihulu Flight Radar")
    window = NativeRadarWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
