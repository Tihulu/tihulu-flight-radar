import json
import time
from pathlib import Path

import pytest

from tihulu_flight_radar.core import (
    DataError, export_json, position_is_fresh, read_local, summarize,
    validate_remote_url, validate_snapshot, visible_aircraft,
)


def sample():
    return {"now": time.time(), "messages": 99, "aircraft": [
        {"hex": "abc123", "flight": "TEST", "seen": 1, "lat": 50.9,
         "lon": 6.7, "seen_pos": 1, "rssi": -25},
        {"hex": "def456", "seen": 1, "rssi": -30},
        {"hex": "dead00", "seen": 100, "lat": 10, "lon": 20, "seen_pos": 100},
    ]}


def test_positions_are_not_invented():
    data = sample()
    assert summarize(data)["aircraft"] == 2
    assert summarize(data)["positioned"] == 1
    assert "lat" not in visible_aircraft(data)[1]


def test_invalid_position_rejected():
    assert not position_is_fresh({"lat": 100, "lon": 1, "seen_pos": 0})
    assert not position_is_fresh({"lat": None, "lon": 1, "seen_pos": 0})
    assert not position_is_fresh({"lat": 1, "lon": 1, "seen_pos": 999})


def test_stale_payload_rejected():
    data = sample()
    data["now"] -= 100
    with pytest.raises(DataError):
        validate_snapshot(data)


def test_file_staleness(tmp_path: Path):
    p = tmp_path / "aircraft.json"
    p.write_text(json.dumps(sample()), encoding="utf-8")
    assert read_local(p)["messages"] == 99


def test_export_is_exact_data(tmp_path: Path):
    data = sample()
    path = tmp_path / "aircraft.json"
    export_json(data, path)
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_url_validation():
    assert validate_remote_url("http://192.168.1.5/data/aircraft.json")
    for url in ("file:///etc/passwd", "ftp://host/data", "http://user:pass@host/x", ""):
        with pytest.raises(DataError):
            validate_remote_url(url)
