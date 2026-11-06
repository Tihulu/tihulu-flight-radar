"""Owner-private native map search location; no change to RTL-SDR receiver site."""
import json

import pytest

from tihulu_flight_radar.bridge import Bridge, validate_search_place
from tihulu_flight_radar.core import DataError


def sample_location():
    return {"lat": 38.6364, "lon": 26.51094, "radius": 150, "zoom": 9,
            "label": "Karaburun · İzmir · Türkiye",
            "name": "Karaburun", "region": "İzmir",
            "country": "TR", "provider": "offline"}


def test_map_location_is_saved_across_bridge_restarts(tmp_path):
    path = tmp_path / "map" / "search-place.json"
    old = Bridge(token="test")
    old._place_path = path
    assert old.get_saved_search_place() is None
    stored = old.save_search_place(sample_location())
    assert stored["radius"] == 150
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["region"] == "İzmir"
    new = Bridge(token="new-different-token")
    new._place_path = path
    assert new.get_saved_search_place() == stored
    # Saved search settings contain no physical RF position or device config.
    assert not {"SiteLat", "SiteLon", "receiver", "rf"} & set(stored)


@pytest.mark.parametrize("patch", [
    {"lat": float("nan")}, {"lat": 100}, {"lon": -190},
    {"radius": 0}, {"radius": 999}, {"radius": 1.5},
    {"country": "ZZ"}, {"label": ""}, {"label": "x"*250},
    {"provider": "\u0001bad"}, {"lat": True},
])
def test_rejects_invalid_or_untrusted_saved_coordinates(tmp_path, patch):
    b = Bridge(token="test")
    b._place_path = tmp_path / "location.json"
    with pytest.raises(DataError):
        b.save_search_place(sample_location() | patch)
    assert not b._place_path.exists()


def test_untrusted_or_corrupt_location_file_is_not_loaded(tmp_path):
    b = Bridge(token="test")
    b._place_path = tmp_path / "location.json"
    b._place_path.write_text("invalid JSON", encoding="utf-8")
    assert b.get_saved_search_place() is None
    b._place_path.write_text("x"*4000, encoding="utf-8")
    assert b.get_saved_search_place() is None


def test_coordinates_accept_global_manual_entries():
    p = sample_location() | {
        "lat": -33.8688, "lon": 151.2093, "country": "",
        "region": "", "name": "Sydney", "provider": "manual"}
    assert validate_search_place(p)["lat"] == -33.8688
