"""Tihulu Flight Radar — real in-application radar window.

The Qt WebEngine window renders the same map as GitHub Pages, but serves it
from a private local bridge and pairs automatically. It never launches the
system web browser or puts a bridge secret in a URL or persistent storage.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import Qt, QUrl
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
        child = QWebEngineView(dialog)
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
        self.bridge = Bridge(allow_control=True)
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
        menu = self.menuBar().addMenu("Receiver")
        classic = QAction("Open full classic receiver dashboard", self)
        classic.triggered.connect(self.open_classic)
        menu.addAction(classic)
        reload_view = QAction("Reload radar view", self)
        reload_view.triggered.connect(self.web.reload)
        menu.addAction(reload_view)
        about = QAction("About sources and permissions", self)
        about.triggered.connect(self._about)
        menu.addAction(about)
        self.statusBar().showMessage(
            "Local radar in this window · readsb reception separate from Internet data"
        )

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
        # Do not stop systemd-managed readsb/tar1090; release only direct child
        # processes owned by the shared receiver controller on app exit.
        if self.classic_window is not None:
            self.classic_window.close()
        self.web.setUrl(QUrl("about:blank"))
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.bridge.receiver.close()
        super().closeEvent(event)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Tihulu Flight Radar")
    window = NativeRadarWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
