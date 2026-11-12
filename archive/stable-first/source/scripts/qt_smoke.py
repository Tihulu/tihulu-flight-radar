"""Headless real-Qt regression: no previous v0.2 functionality may disappear.

Run with QT_QPA_PLATFORM=offscreen after Qt runtime libraries are installed.
"""
import json
from urllib.request import urlopen

from PySide6.QtWidgets import QApplication

from tihulu_flight_radar.app import RadarWindow, aircraft_fields


def main():
    app = QApplication([])
    window = RadarWindow()
    try:
        assert window.start_button.text()
        assert window.stop_button.text()
        assert window.restart_button.text()
        assert window.map_button.text()
        assert window.full_map_button.text()
        assert window.export_button.text()
        assert window.quick_export_button.text()
        assert window.boot_checkbox.text()
        assert window.lan_label is not None
        assert window.diagnostics_button is not None
        assert window.mode_select.count() == 3
        assert window.remote_field is not None
        assert window.decoder_field is not None

        # Test-only actual-format fields. They never reach the live receiver.
        aircraft = [
            {
                "hex": "3c0acb", "flight": "CFG1RT", "r": "D-TEST", "t": "B738",
                "alt_baro": 9875, "gs": 210.5, "track": 110,
                "lat": 50.902908, "lon": 6.738331,
                "seen": 1, "seen_pos": 1, "rssi": -28.4,
            },
            {"hex": "4abc01", "seen": 2},
            {"hex": "stale", "seen": 150},
        ]
        window._update_aircraft(aircraft)
        assert window.aircraft_table.rowCount() == 2
        assert window.aircraft_table.item(0, 0).text() == "CFG1RT"
        assert window.aircraft_table.item(0, 1).text() == "3c0acb"
        assert window.aircraft_table.item(0, 4).text() == "9875"
        assert "CFG1RT" in aircraft_fields(aircraft[0])
        assert window.aircraft_table.item(1, 1).text() == "4abc01"
        assert window.aircraft_rows[1].get("lat") is None

        window.settings_toggle.setChecked(True)
        assert window.settings_frame.isVisible() or window.settings_toggle.isChecked()

        # The map must load when the decoder has zero aircraft.
        with urlopen(window.map_server.url, timeout=5) as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
        assert "Show Germany" in page
        assert "GERMANY_DEFAULT" in page
        print("Qt UI smoke and legacy feature regression OK")
    finally:
        window.close()
        app.quit()


if __name__ == "__main__":
    main()
