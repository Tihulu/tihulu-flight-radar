"""Verified local-only persistent RF history does not have a 64-fix cap."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tihulu_flight_radar.rf_history_store import RFHistoryStore, radio_fix


class RFHistoryStoreTests(unittest.TestCase):
    @staticmethod
    def aircraft(hex="a00001", lat=50.91, lon=6.95, alt=30000):
        return {"hex":hex,"lat":lat,"lon":lon,
                "alt_baro":alt,"seen":0.3,"seen_pos":0.5,
                "gs":310,"track":125}

    def test_only_fresh_position_and_sane_altitude_can_be_logged(self):
        import time
        now = round(time.time()*1000)
        self.assertIsNotNone(radio_fix(self.aircraft(), now))
        invalid = self.aircraft()
        invalid["seen_pos"] = 75
        self.assertIsNone(radio_fix(invalid, now))
        invalid = self.aircraft(alt=100)
        self.assertIsNone(radio_fix(invalid, now))
        invalid = self.aircraft(hex="not-hex")
        self.assertIsNone(radio_fix(invalid, now))

    def test_opt_in_pause_persistence_sessions_and_pagination(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp)/"rf.sqlite3"
            store = RFHistoryStore(db_path)
            self.assertFalse(store.enabled, "Recorder is OFF on startup")
            self.assertEqual(store.append([self.aircraft()]),0)
            first = store.config("start")
            sid = first["activeSessionId"]
            self.assertIsInstance(sid,int)
            self.assertEqual(store.append([self.aircraft()]),1)
            self.assertEqual(store.append([self.aircraft()]),0,
                             "Repeated nearby snapshot must not bloat archive")
            self.assertEqual(store.append([self.aircraft(lat=51.01)]),1)
            page = store.page(sid,0,1)
            self.assertEqual(len(page["records"]),1)
            self.assertTrue(page["hasMore"])
            second = store.page(sid,page["nextAfterId"],100)
            self.assertEqual(len(second["records"]),1)
            self.assertFalse(second["hasMore"])
            self.assertTrue(all(r["recorded_rf"] for r in second["records"]))
            store.config("pause")
            self.assertFalse(store.enabled)
            reopened = RFHistoryStore(db_path)
            self.assertFalse(reopened.enabled)
            self.assertEqual(reopened.status()["observations"],2)
            next_session = reopened.config("new-session")["activeSessionId"]
            self.assertNotEqual(sid,next_session)
            self.assertEqual(reopened.page(sid,0,100)["records"][0]["hex"],"a00001")

    def test_same_millisecond_distant_fix_is_not_dropped(self):
        # Reproduces intermittent Ubuntu CI failure without relying on timing.
        with tempfile.TemporaryDirectory() as temp:
            store = RFHistoryStore(Path(temp)/"rf.sqlite3")
            sid = store.config("start")["activeSessionId"]
            with patch("tihulu_flight_radar.rf_history_store.time.time",
                       return_value=1700000000):
                self.assertEqual(store.append([self.aircraft()]), 1)
                self.assertEqual(store.append([self.aircraft()]), 0)
                self.assertEqual(store.append([self.aircraft(lat=51.01)]), 1)
            self.assertEqual(len(store.page(sid, 0, 10)["records"]), 2)

    def test_no_fixed_64_record_count_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            store = RFHistoryStore(Path(temp)/"rf.sqlite3")
            sid=store.config("start")["activeSessionId"]
            rows=[]
            for i in range(100):
                rows.append(self.aircraft(hex=f"{i:06x}",lat=50.0+(i%40)*.12))
            self.assertEqual(store.append(rows),100)
            page=store.page(sid,0,5000)
            self.assertEqual(len(page["records"]),100)

    def test_low_disk_space_pauses_without_deleting(self):
        with tempfile.TemporaryDirectory() as temp:
            store=RFHistoryStore(Path(temp)/"rf.sqlite3")
            store.config("start")
            from collections import namedtuple
            usage=namedtuple("DiskUsage","total used free")(1000,999,1)
            with patch("tihulu_flight_radar.rf_history_store.shutil.disk_usage",
                       return_value=usage):
                self.assertEqual(store.append([self.aircraft()]),0)
            self.assertFalse(store.enabled)
            self.assertIn("2 GiB",store.last_error)


if __name__=="__main__":
    unittest.main()
