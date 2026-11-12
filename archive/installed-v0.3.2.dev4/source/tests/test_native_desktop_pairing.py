"""Regression checks for Qt desktop pairing without SDR or Qt hardware."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class DesktopPairingTests(unittest.TestCase):
    def test_qt_bridge_retries_when_web_script_not_ready(self):
        source=(ROOT/"tihulu_flight_radar"/"native.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("window.tihuluNativeConnect",source)
        self.assertIn("return 'waiting'",source)
        self.assertIn("attempt < 16",source)
        self.assertIn("Reconnect local bridge",source)
        self.assertIn("document.documentElement.classList.add('native')",source)
        self.assertNotIn("self.local_url + '?token='",source)

    def test_decoder_start_is_rechecked_before_success(self):
        source=(ROOT/"tihulu_flight_radar"/"native.py").read_text(encoding="utf-8")
        self.assertIn("started = self.bridge.receiver.start()",source)
        self.assertIn("active, detail = self.bridge.receiver.status()",source)
        self.assertIn("Receiver did not stay running after start",source)

    def test_standalone_main_and_old_stable_branch_untouched(self):
        source=(ROOT/"scripts"/"install-linux.sh").read_text(encoding="utf-8")
        self.assertIn('TIHULU_REF:-main',source)
        self.assertIn("pipx install --force",source)


if __name__=="__main__":
    unittest.main()
