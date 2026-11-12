"""Tihulu Flight Radar — real in-application radar window.

The Qt WebEngine window renders the same map as GitHub Pages, but serves it
from a private local bridge and pairs automatically. It never launches the
system web browser or puts a bridge secret in a URL or persistent storage.
"""
from __future__ import annotations

import json
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import Qt, QUrl, QSettings, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWebEngineCore import QWebEnginePermission
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QVBoxLayout, QFileDialog

from .bridge import Bridge, make_handler
from .control import MixedOwnershipWarning


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
        # Give the full tar viewer its own bounded feed cache. Previously it
        # shared the main map's single-key 35-second cooldown, so querying a
        # different tar1090 viewport returned no aircraft despite a healthy
        # Internet feed in the main window.
        child = TarOverlayView(dialog, assume_tar=True)
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
        from .control import MODES, linux_readsb_unit_installed
        import platform
        import shutil
        preferred = str(self.settings.value("mode", self.bridge.receiver.mode))
        remote = str(self.settings.value("remote", ""))
        decoder = str(self.settings.value("decoder", ""))
        if preferred == "Remote JSON" and not remote.strip():
            preferred = self.bridge.receiver.mode
        # Users with a working standalone readsb often have no systemd
        # readsb.service; do not silently show an empty RF layer in that case.
        if (preferred == "Linux services" and platform.system() == "Linux"
                and not linux_readsb_unit_installed()
                and (shutil.which("readsb")
                     or Path("/usr/bin/readsb").is_file()
                     or Path("/usr/local/bin/readsb").is_file())):
            preferred = "Direct readsb"
            self.settings.setValue("mode", preferred)
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
        self._listener_closed = False
        self.local_url = f"http://127.0.0.1:{self.server.server_port}"

        self.web = EmbeddedRadarView(self)
        self.setCentralWidget(self.web)
        self.web.loadFinished.connect(self._paired_on_loaded)
        # Qt WebEngine may not save blob: downloads without an explicit
        # downloadRequested handler. Keep exports in a user-chosen local path.
        self.web.page().profile().downloadRequested.connect(self._save_web_download)
        self.web.page().permissionRequested.connect(self._location_permission_requested)
        # This desktop installation can start in the selected region without
        # misrepresenting it as the real antenna position or requesting GPS.
        region = str(self.settings.value("start_region", "cologne")).lower()
        if region not in ("cologne", "germany"):
            region = "germany"
        self.web.setUrl(QUrl(self.local_url + "/?region=" + region))

        self.classic_window = None
        self._startup_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tihulu-rf-start")
        self._startup_future = None
        self._exit_requested = False
        self._quit_done = False
        self._quit_deadline = None
        self._quit_warning_shown = False
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
            self.settings.value("auto_start_receiver", False, type=bool)
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
        quit_action = QAction("Quit Flight Radar (release owned resources)", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)
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

    def _location_permission_requested(self, permission):
        # The main application may request location for startup viewport only.
        # Never grant it silently, and never permit another origin to receive
        # location. Denial falls back to the nearest real RF plane or Cologne.
        origin = permission.origin()
        if (permission.permissionType()
                != QWebEnginePermission.PermissionType.Geolocation):
            permission.deny()
            return
        if (origin.scheme() != "http" or origin.host() != "127.0.0.1"
                or origin.port() != self.server.server_port):
            permission.deny()
            return
        choice = QMessageBox.question(
            self, "Flight Radar location",
            "Use your current location as the initial radar map center?\n"
            "If unavailable or declined, the app will focus on the nearest "
            "radio-received aircraft; otherwise Cologne.\n"
            "This does not change the SDR receiver's physical site location.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            permission.grant()
        else:
            permission.deny()

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
        if f is None:
            return
        if not f.done():
            # This timer runs while a worker is pending. A single closeEvent
            # cannot observe a 45-second timeout without this check.
            if (self._exit_requested and self._quit_deadline is not None
                    and time.monotonic() >= self._quit_deadline
                    and not self._quit_warning_shown):
                self._quit_warning_shown = True
                QMessageBox.warning(
                    self, "Quit still draining",
                    "App-owned receiver startup has not completed within "
                    "45 seconds. No new Start is admitted; Quit remains "
                    "incomplete until the worker finishes or is resolved."
                )
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

    def _save_web_download(self, request):
        """Confirm a local destination for a user-initiated browser download.

        This is especially important for JSON/CSV RF timing laboratory exports
        from a blob: URL. No data is sent to an external service.
        """
        filename = Path(request.downloadFileName()).name or "flight-radar-export"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Flight Radar export",
            str(Path.home() / "Downloads" / filename),
        )
        if not path:
            request.cancel()
            return
        target = Path(path).expanduser()
        request.setDownloadDirectory(str(target.parent))
        request.setDownloadFileName(target.name)
        request.accept()

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

    def _close_local_listener(self):
        """Bounded, retryable shutdown for this window's loopback HTTP socket."""
        if not self._listener_closed:
            try:
                self.server.shutdown()
            finally:
                self.server.server_close()
            self._listener_closed = True
        self.server_thread.join(timeout=2)
        if self.server_thread.is_alive():
            raise RuntimeError(
                "The app-owned local HTTP listener thread is still alive "
                "after 2 seconds; retry Quit."
            )

    def closeEvent(self, event):
        if self._quit_done:
            super().closeEvent(event)
            return
        # Set both gates before waiting for a pending Start or HTTP request.
        self._exit_requested = True
        self.bridge.request_quit()
        if self._quit_deadline is None:
            self._quit_deadline = time.monotonic() + 45
        if self._startup_future is not None and not self._startup_future.done():
            self._startup_future.cancel()
            event.ignore()
            self.statusBar().showMessage("Finishing app-owned receiver startup before Quit…")
            if time.monotonic() >= self._quit_deadline and not self._quit_warning_shown:
                self._quit_warning_shown = True
                QMessageBox.warning(self, "Quit still draining",
                    "A receiver start has not finished within 45 seconds. "
                    "Quit is incomplete, but no new Start can be accepted.")
            return
        # The classic dashboard shares our receiver; it may still have an
        # action/JSON/map future. It must close its own pool/port first.
        if self.classic_window is not None and not self.classic_window.close():
            event.ignore()
            if time.monotonic() < self._quit_deadline:
                QTimer.singleShot(250, self.close)
            elif not self._quit_warning_shown:
                self._quit_warning_shown = True
                QMessageBox.warning(self, "Quit still draining",
                    "The classic receiver dashboard has outstanding tasks. "
                    "Quit is incomplete; retry after those workers finish.")
            return
        self._startup_timer.stop()
        self._startup_pool.shutdown(wait=True, cancel_futures=True)
        # Stop new HTTP connections before attempting receiver close. The
        # bridge then verifies that admitted request-handler threads drained.
        listener_error = None
        try:
            self._close_local_listener()
        except (OSError, RuntimeError) as exc:
            listener_error = str(exc)
        receiver_error = None
        receiver_mixed_only = False
        try:
            # Controller/bridge preserves PR #15's external/mixed ownership.
            self.bridge.close(
                release_local_service=self.release_action.isChecked()
            )
        except MixedOwnershipWarning as exc:
            receiver_mixed_only = True
            receiver_error = str(exc)
        except Exception as exc:
            receiver_error = str(exc)
        # A successful Quit can still leave a GLOBAL readsb/tar1090 receiver
        # running for another application. Surface this independently of a
        # fatal private-cleanup error; never claim the SDR was freed.
        shared_note = getattr(
            getattr(self.bridge, "receiver", None), "last_service_release_note", None
        )
        if listener_error or receiver_error or shared_note:
            problems = [x for x in (listener_error, receiver_error) if x]
            if shared_note and not receiver_error:
                problems.append(shared_note)
            title = ("Quit cleanup incomplete" if listener_error or receiver_error
                     else "Shared receiver preserved")
            QMessageBox.warning(self, title, "\n".join(problems))
            if listener_error or (receiver_error and not receiver_mixed_only):
                event.ignore()
                return  # No false success when a local resource remains.
        # External tar1090, user settings and saved exports are untouched.
        for popup in list(self.web._popups):
            popup.close()
        self.web.setUrl(QUrl("about:blank"))
        self._quit_done = True
        super().closeEvent(event)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Tihulu Flight Radar")
    window = NativeRadarWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
