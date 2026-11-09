"""Read-only raster MBTiles support for the loopback native radar.

No scraping, prefetching or OSM tile bulk download. Users obtain archives
from providers permitting offline redistribution or import their own files.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

MAP_ROOT = Path.home() / ".local/share/tihulu-flight-radar/maps"
MAP_DIRECTORIES = (MAP_ROOT, Path.home() / "Maps", Path.home() / "Downloads")
MAX_MAP_BYTES = 1_073_741_824
MAX_TILE_BYTES = 2_097_152
SAFE_NAME = re.compile(r"^[\w ()\[\].-]{1,120}\.mbtiles$", re.ASCII | re.IGNORECASE)
FORMAT_MIME = {"png": "image/png", "jpg": "image/jpeg",
               "jpeg": "image/jpeg", "webp": "image/webp"}


def _open(path: Path):
    # immutable, query_only and mode=ro prevent modifications or arbitrary SQL
    # from an untrusted archive. Reject symlink escapes before opening.
    path = path.resolve(strict=True)
    return sqlite3.connect("file:" + quote(str(path), safe="/") +
                           "?mode=ro&immutable=1", uri=True, timeout=2)


def metadata(path: Path) -> dict | None:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_MAP_BYTES:
            return None
        with _open(path) as db:
            db.execute("PRAGMA query_only=ON")
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            if "tiles" not in tables or "metadata" not in tables:
                return None
            meta = dict(db.execute("SELECT name,value FROM metadata LIMIT 64"))
            fmt = str(meta.get("format", "")).lower()
            if fmt not in FORMAT_MIME:
                return None
            if not {"zoom_level", "tile_column", "tile_row", "tile_data"}.issubset(
                    {r[1] for r in db.execute("PRAGMA table_info(tiles)")}):
                return None
        return {"name": path.name, "format": fmt,
                "title": str(meta.get("name") or path.stem)[:110],
                "minzoom": str(meta.get("minzoom", "?"))[:4],
                "maxzoom": str(meta.get("maxzoom", "?"))[:4]}
    except (OSError, sqlite3.Error, ValueError):
        return None


def discover() -> list[tuple[Path, dict]]:
    results = []
    seen = set()
    for directory in MAP_DIRECTORIES:
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.mbtiles"))[:32]:
            if not SAFE_NAME.fullmatch(file.name) or file.is_symlink():
                continue
            key = file.resolve()
            if key in seen:
                continue
            seen.add(key)
            info = metadata(file)
            if info:
                results.append((file, info))
    return results[:64]


def select(name: str | None) -> tuple[Path, dict] | None:
    archives = discover()
    if not archives:
        return None
    if name:
        return next((row for row in archives if row[1]["name"] == name), None)
    return archives[0]


def read_tile(map_file: Path, z: int, x: int, y: int) -> tuple[bytes, str] | None:
    info = metadata(map_file)
    if not info or not 0 <= z <= 16 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        return None
    try:
        with _open(map_file) as db:
            db.execute("PRAGMA query_only=ON")
            record = db.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? "
                "AND tile_column=? AND tile_row=? LIMIT 1",
                (z, x, 2**z - 1 - y)).fetchone()  # MBTiles stores TMS y
            if record and isinstance(record[0], bytes) and len(record[0]) <= MAX_TILE_BYTES:
                return record[0], FORMAT_MIME[info["format"]]
    except (sqlite3.Error, OSError):
        pass
    return None
