"""Persistent, opt-in direct-receiver RF history, never Internet aircraft.

SQLite records minimal, verified, position-bearing ADS-B constraints. No 64
record cap, no TTL, and no silent deletion. Native and paired local bridge
share the same store. Logging is always OFF when a new process starts.
"""
from __future__ import annotations

import math
import shutil
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path.home() / ".local/share/tihulu-flight-radar/rf-history.sqlite3"
WARN_BYTES = 1_073_741_824
MIN_FREE_BYTES = 2_147_483_648
EARTH_KM = 6371.0088


def _num(v):
    return type(v) in (int, float) and math.isfinite(v)


def _dist(a, b):
    rad = math.pi / 180
    dp = (a[0] - b[0]) * rad
    dl = (a[1] - b[1]) * rad
    h = (math.sin(dp/2)**2 + math.cos(a[0]*rad)*math.cos(b[0]*rad)
         * math.sin(dl/2)**2)
    return 2*EARTH_KM*math.asin(min(1, math.sqrt(max(0, h))))


def radio_fix(plane: dict, now_ms: int) -> tuple | None:
    """Only real local readsb observations; caller never passes online data."""
    if not isinstance(plane, dict):
        return None
    hexa = plane.get("hex")
    if not isinstance(hexa, str) or len(hexa) != 6 or any(
        x not in "0123456789abcdefABCDEF" for x in hexa
    ):
        return None
    lat, lon = plane.get("lat"), plane.get("lon")
    if not (_num(lat) and _num(lon) and abs(lat) <= 85 and abs(lon) <= 180):
        return None
    seen, seen_pos = plane.get("seen"), plane.get("seen_pos")
    if not (_num(seen) and 0 <= seen <= 10 and _num(seen_pos)
            and 0 <= seen_pos <= 5):
        return None
    alt = plane.get("alt_geom")
    if not _num(alt):
        alt = plane.get("alt_baro")
    if not _num(alt) or not 1000 <= alt <= 65000:
        return None
    # Same geometric horizon upper-bound formula as receiver_coverage.js.
    effective = EARTH_KM*4/3
    height = alt*0.0003048
    receiver_height = 0.03
    radius = (math.sqrt(2*effective*height+height**2) +
              math.sqrt(2*effective*receiver_height+receiver_height**2)+30)
    if not 10 <= radius <= 1600:
        return None
    return (hexa.lower(), now_ms-round(seen_pos*1000), float(lat), float(lon),
            float(alt), radius,
            float(plane["gs"]) if _num(plane.get("gs")) else None,
            float(plane["track"]) if _num(plane.get("track")) else None)


class RFHistoryStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.lock = threading.RLock()
        self.enabled = False
        self.session_id: int | None = None
        self.last_error = ""
        self._last: dict[str, tuple] = {}
        self._prepare()

    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=6)
        conn.execute("PRAGMA busy_timeout=6000")
        return conn

    def _prepare(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._connect() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS sessions(
                    id INTEGER PRIMARY KEY, started_ms INTEGER NOT NULL,
                    ended_ms INTEGER, label TEXT NOT NULL DEFAULT '')""")
                db.execute("""CREATE TABLE IF NOT EXISTS fixes(
                    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,
                    hex TEXT NOT NULL, observed_ms INTEGER NOT NULL,
                    lat REAL NOT NULL, lon REAL NOT NULL,
                    alt_ft REAL NOT NULL, radius_km REAL NOT NULL,
                    speed_kt REAL, heading_deg REAL,
                    UNIQUE(session_id,hex,observed_ms,lat,lon))""")
                db.execute("""CREATE INDEX IF NOT EXISTS idx_rf_fixes_session_id
                    ON fixes(session_id,id)""")
                db.execute("""CREATE INDEX IF NOT EXISTS idx_rf_fixes_epoch
                    ON fixes(session_id,observed_ms)""")
                db.execute("""CREATE INDEX IF NOT EXISTS idx_rf_fixes_aircraft
                    ON fixes(session_id,hex,id)""")

    def config(self, action: str) -> dict:
        with self.lock:
            if action not in ("start", "pause", "new-session"):
                raise ValueError("Unsupported History Recorder action.")
            if action == "pause":
                self.enabled = False
            else:
                if action == "new-session":
                    self.enabled = False
                    self.session_id = None
                    self._last.clear()
                if self.session_id is None:
                    with self._connect() as db:
                        c = db.execute("INSERT INTO sessions(started_ms) VALUES(?)",
                                       (int(time.time()*1000),))
                        self.session_id = int(c.lastrowid)
                self.enabled = True
            self.last_error = ""
            return self.status()

    def append(self, rows: list[dict]):
        if not self.enabled:
            return 0
        with self.lock:
            if not self.enabled or self.session_id is None:
                return 0
            try:
                free = shutil.disk_usage(self.path.parent).free
                if free < MIN_FREE_BYTES:
                    self.enabled = False
                    self.last_error = "Recording paused: less than 2 GiB disk space available."
                    return 0
                now = int(time.time()*1000)
                accepted = []
                for plane in rows[:10000]:
                    fix = radio_fix(plane, now)
                    if fix is None:
                        continue
                    hex_, stamp, lat, lon, altitude, radius, gs, track = fix
                    old = self._last.get(hex_)
                    if old is not None:
                        # Keep informative flight-path fixes; avoid writing the
                        # same parked/unchanged position every polling interval.
                        _, old_stamp, old_lat, old_lon, *_ = old
                        if (stamp <= old_stamp or
                                _dist((lat,lon),(old_lat,old_lon)) < 5):
                            continue
                    self._last[hex_] = fix
                    accepted.append((self.session_id, *fix))
                if accepted:
                    with self._connect() as db:
                        db.executemany("""INSERT OR IGNORE INTO fixes(
                           session_id,hex,observed_ms,lat,lon,alt_ft,
                           radius_km,speed_kt,heading_deg)
                           VALUES(?,?,?,?,?,?,?,?,?)""", accepted)
                return len(accepted)
            except (OSError, sqlite3.Error) as exc:
                self.enabled = False
                self.last_error = "History write failed: " + str(exc)[:180]
                return 0

    def status(self) -> dict:
        with self.lock:
            with self._connect() as db:
                sessions = [dict(id=x[0],started_ms=x[1],observations=x[2])
                            for x in db.execute(
                             """SELECT s.id,s.started_ms,COUNT(f.id) FROM sessions s
                                LEFT JOIN fixes f ON f.session_id=s.id
                                GROUP BY s.id ORDER BY s.id DESC LIMIT 40""")]
            return {
                "recording": self.enabled, "activeSessionId": self.session_id,
                "sessions": sessions,
                "observations": sum(item["observations"] for item in sessions),
                "diskBytes": self.path.stat().st_size if self.path.exists() else 0,
                "warning": ("Archive exceeds 1 GiB. No data deleted."
                            if self.path.exists() and self.path.stat().st_size >= WARN_BYTES
                            else self.last_error),
                "source": "local genuine receiver only",
            }

    def page(self, session_id: int, after_id: int = 0, limit: int = 5000) -> dict:
        if type(session_id) is not int or session_id <= 0 or type(after_id) is not int or after_id < 0:
            raise ValueError("Invalid History session or cursor.")
        if type(limit) is not int or not 1 <= limit <= 5000:
            raise ValueError("History page limit must be 1–5000.")
        with self.lock, self._connect() as db:
            rows = db.execute("""SELECT id,hex,observed_ms,lat,lon,alt_ft,
                                  radius_km,speed_kt,heading_deg
                                  FROM fixes WHERE session_id=? AND id>?
                                  ORDER BY id ASC LIMIT ?""",
                              (session_id,after_id,limit)).fetchall()
        data = [{"id":r[0],"hex":r[1],"capturedAtMs":r[2],
                 "lat":r[3],"lon":r[4],"altitudeFeet":r[5],
                 "radiusKm":r[6],"speedKt":r[7],"headingDeg":r[8],
                 "recorded_rf":True} for r in rows]
        return {"records":data,"nextAfterId":rows[-1][0] if rows else after_id,
                "hasMore":len(rows)==limit,"sessionId":session_id}
