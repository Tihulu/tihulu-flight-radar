"""A selected callsign can reveal route airports, never timetable data."""
import io
import json
import unittest

from tihulu_flight_radar.flight_route_lookup import (
    CallsignRouteLookup, airport, normalize_route, validate_callsign,
)


class _Response:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return io.BytesIO(self.body)
    def __exit__(self, *args):
        return False


class _Opener:
    def __init__(self, data):
        self.data = data
        self.calls = 0
    def open(self, req, timeout):
        self.calls += 1
        assert req.full_url.startswith("https://api.adsbdb.com/v0/callsign/")
        assert timeout <= 4
        return _Response(json.dumps(self.data).encode("utf-8"))


class AircraftJourneyLookupTests(unittest.TestCase):
    route = {"response":{"flightroute":{
        "callsign":"DLH1234","origin":{"iata_code":"CGN","icao_code":"EDDK",
          "name":"Cologne Bonn"},
        "destination":{"iata_code":"IST","icao_code":"LTFM","municipality":"Istanbul"}
    }}}

    def test_callsign_allowlist_rejects_ssrf_and_unknown(self):
        self.assertEqual(validate_callsign("DLH1234"),"DLH1234")
        for invalid in ("https://bad.example/", "../../x", "dlh123", "DLH!123",
                        "CGN\nAuthorization: x", "", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_callsign(invalid)

    def test_matching_route_has_airports_but_no_fabricated_schedule(self):
        result=normalize_route(self.route,"DLH1234")
        flight=result["response"]["flightroute"]
        self.assertEqual(flight["origin"]["iata_code"],"CGN")
        self.assertEqual(flight["destination"]["icao_code"],"LTFM")
        self.assertNotIn("scheduled",flight)
        self.assertNotIn("actual",flight)
        self.assertEqual(normalize_route(self.route,"THY5432")
                         ["response"]["flightroute"],None)

    def test_bounded_memory_only_cache(self):
        opener=_Opener(self.route)
        lookup=CallsignRouteLookup(opener=opener)
        first=lookup.query("DLH1234")
        self.assertEqual(first,lookup.query("DLH1234"))
        self.assertEqual(opener.calls,1)
        self.assertEqual(len(lookup.cache),1)

    def test_unverified_no_route_is_not_invented(self):
        self.assertIsNone(airport({"name":"Not an airport"}))
        result=normalize_route({"response":{"flightroute":None}},"DLH1234")
        self.assertIsNone(result["response"]["flightroute"])


if __name__=="__main__":
    unittest.main()
