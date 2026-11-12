"""Regression tests for local-only raster MBTiles discovery and TMS tile inversion."""
import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from tihulu_flight_radar import offline_maps


class OfflineMapTests(unittest.TestCase):
    def test_valid_raster_archive_and_tms_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            map_file = root / "Cologne.mbtiles"
            with closing(sqlite3.connect(map_file)) as db:
                db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
                db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER,"
                           "tile_row INTEGER, tile_data BLOB)")
                db.executemany("INSERT INTO metadata VALUES (?,?)", [
                    ("name", "Cologne raster"), ("format", "png"),
                    ("minzoom", "1"), ("maxzoom", "5")])
                # XYZ 1/0/0 is stored as MBTiles TMS y=1.
                db.execute("INSERT INTO tiles VALUES (1,0,1,?)",
                           (b"\x89PNG\r\n\x1a\nvalid tile",))
                db.commit()
                db.commit()  # closing() closes without an implicit transaction commit
            with patch.object(offline_maps, "MAP_DIRECTORIES", (root,)):
                hits = offline_maps.discover()
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0][1]["title"], "Cologne raster")
                self.assertEqual(offline_maps.select("Cologne.mbtiles"), hits[0])
                self.assertIsNone(offline_maps.select("Unknown.mbtiles"))
                data = offline_maps.read_tile(map_file, 1, 0, 0)
                self.assertIsNotNone(data)
                self.assertEqual(data[0], b"\x89PNG\r\n\x1a\nvalid tile")
                self.assertEqual(data[1], "image/png")
                self.assertIsNone(offline_maps.read_tile(map_file, 1, 0, 1))
                self.assertIsNone(offline_maps.read_tile(map_file, 20, 0, 0))

    def test_reject_vector_and_invalid_or_symlink_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            invalid = root / "nonmap.mbtiles"
            invalid.write_bytes(b"not sqlite")
            vector = root / "vector.mbtiles"
            with closing(sqlite3.connect(vector)) as db:
                db.execute("CREATE TABLE metadata (name TEXT,value TEXT)")
                db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER,"
                           "tile_row INTEGER, tile_data BLOB)")
                db.execute("INSERT INTO metadata VALUES ('format','pbf')")
                db.commit()
            (root / "linked.mbtiles").symlink_to(vector)
            with patch.object(offline_maps, "MAP_DIRECTORIES", (root,)):
                self.assertEqual(offline_maps.discover(), [])
                self.assertIsNone(offline_maps.metadata(vector))
                self.assertIsNone(offline_maps.metadata(invalid))


if __name__ == "__main__":
    unittest.main()
