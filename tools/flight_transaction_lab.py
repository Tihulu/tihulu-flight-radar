#!/usr/bin/env python3
"""CI-ONLY transaction laboratory for a future Flight Radar side-by-side installer.

There is NO production --install option. Only --plan is exposed to CLI users.
All write-capable functions require disposable GitHub CI, and operate strictly
under RUNNER_TEMP/flight-transaction-lab/<fixture-name>, never user HOME.
No pip, sudo, systemctl, app imports, external URLs, SDR, Qt or user data.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
OWNER = "TIHULU_FLIGHT_TRANSACTION_LAB_V1"
MAX_SIZE = 1024 * 1024


def fail(message: str):
    raise RuntimeError(message)


def _exists(path: Path) -> bool:
    return path.is_symlink() or path.exists()


def _check_path(path: Path, *, expected_directory: bool = True):
    if path.is_symlink():
        fail(f"Symlink is forbidden: {path}")
    if _exists(path) and expected_directory and not path.is_dir():
        fail(f"Unexpected non-directory: {path}")


def _write_new(path: Path, payload: bytes):
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_atomic(path: Path, payload: bytes):
    temp = path.parent / (".tx-" + uuid.uuid4().hex)
    try:
        _write_new(temp, payload)
        os.replace(temp, path)
    finally:
        if _exists(temp) and not temp.is_symlink():
            temp.unlink()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


class TransactionLab:
    def __init__(self, root: Path):
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
            fail("CI-only laboratory; no workstation installation is possible")
        runner = os.environ.get("RUNNER_TEMP")
        if not runner:
            fail("RUNNER_TEMP is required")
        base = Path(runner)
        if not base.is_absolute() or not root.is_absolute():
            fail("Absolute disposable paths are required")
        if not NAME.fullmatch(root.name):
            fail("Invalid fixture name")
        if root.parent != base / "flight-transaction-lab":
            fail("Fixture must be a direct child of RUNNER_TEMP/flight-transaction-lab")
        for candidate in (base, root.parent, root):
            _check_path(candidate)
        self.root = root
        self.releases = root / "releases"
        self.current = root / "current"
        self.state_path = root / "state.json"
        self.pending = root / "pending.json"
        self.lock_path = root / "lab.lock"

    @contextlib.contextmanager
    def locked(self):
        _check_path(self.root)
        self.root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.releases.mkdir(mode=0o700, exist_ok=True)
        for path in (self.releases, self.root):
            _check_path(path)
        if self.lock_path.is_symlink():
            fail("Cannot lock via symlink")
        with self.lock_path.open("a+b") as fd:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            yield
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)

    def _read_state(self) -> dict:
        if not _exists(self.state_path):
            return {"owner": OWNER, "active": None, "previous": None}
        if self.state_path.is_symlink():
            fail("Foreign state symlink")
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("owner") != OWNER:
            fail("Foreign or corrupt transaction state")
        for key in ("active", "previous"):
            if state.get(key) is not None and not NAME.fullmatch(state[key]):
                fail("Invalid state release name")
        return state

    def _current(self) -> str | None:
        if not _exists(self.current):
            return None
        if not self.current.is_symlink():
            fail("Refusing non-symlink current pointer")
        link = os.readlink(self.current)
        if not link.startswith("releases/"):
            fail("Foreign current symlink destination")
        name = link[len("releases/"):]
        if not NAME.fullmatch(name) or link != "releases/" + name:
            fail("Current symlink escaped release namespace")
        return name

    def _verify_release(self, name: str):
        if not NAME.fullmatch(name):
            fail("Invalid release")
        release = self.releases / name
        _check_path(release)
        if not release.is_dir():
            fail("Missing release")
        marker = release / "manifest.json"
        payload = release / "image.bin"
        for item in (marker, payload):
            if item.is_symlink() or not item.is_file():
                fail("Missing, symlinked or foreign release artifact")
        expected = json.loads(marker.read_text(encoding="utf-8"))
        raw = payload.read_bytes()
        if (expected != {"owner": OWNER, "name": name, "sha256": hashlib.sha256(raw).hexdigest(),
                         "size": len(raw)} or len(raw) > MAX_SIZE):
            fail("Release manifest does not match fixture bytes")
        if sorted(p.name for p in release.iterdir()) != ["image.bin", "manifest.json"]:
            fail("Foreign release contents")
        return expected

    def stage_fixture(self, name: str, payload: bytes):
        """Prepare untrusted *test bytes*; no app package or installation."""
        if not NAME.fullmatch(name):
            fail("Invalid fixture release name")
        if not payload or len(payload) > MAX_SIZE:
            fail("Fixture size out of bounds")
        with self.locked():
            if _exists(self.pending):
                fail("Pending transaction requires recover")
            final = self.releases / name
            if _exists(final):
                fail("Release already exists; do not overwrite")
            stage = self.releases / (".stage-" + uuid.uuid4().hex)
            stage.mkdir(mode=0o700)
            try:
                _write_new(stage / "image.bin", payload)
                _write_new(stage / "manifest.json", _json_bytes({
                    "owner": OWNER, "name": name, "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }))
                stage.rename(final)
            finally:
                if stage.is_dir() and not stage.is_symlink():
                    for item in stage.iterdir():
                        item.unlink()
                    stage.rmdir()

    def _set_pointer(self, name: str | None):
        if self.current.is_symlink():
            current = self._current()
            if current is None:
                fail("Invalid pointer")
        elif _exists(self.current):
            fail("Refusing to overwrite non-link current entry")
        if name is None:
            if self.current.is_symlink():
                self.current.unlink()
            return
        temp = self.root / (".pointer-" + uuid.uuid4().hex)
        os.symlink("releases/" + name, temp)
        try:
            os.replace(temp, self.current)
        finally:
            if temp.is_symlink():
                temp.unlink()

    def _verify_consistency(self) -> dict:
        state = self._read_state()
        if _exists(self.pending):
            fail("Unfinished transaction: call recover, never auto-overwrite")
        if self._current() != state["active"]:
            fail("State/current pointer mismatch")
        if state["active"] is not None:
            self._verify_release(state["active"])
        return state

    def switch(self, name: str | None, *, fault: str | None = None):
        """Activate fixture, rollback or deactivate; never remove a release."""
        if name is not None and not NAME.fullmatch(name):
            fail("Invalid switch target")
        with self.locked():
            state = self._verify_consistency()
            if name is not None:
                self._verify_release(name)
            if name == state["active"]:
                return
            journal = {"owner": OWNER, "before": state, "to": name}
            _write_atomic(self.pending, _json_bytes(journal))
            if fault == "after_journal":
                raise RuntimeError("Injected fault after journal")
            self._set_pointer(name)
            if fault == "after_pointer":
                raise RuntimeError("Injected fault after pointer")
            updated = {"owner": OWNER, "active": name, "previous": state["active"]}
            _write_atomic(self.state_path, _json_bytes(updated))
            if fault == "after_state":
                raise RuntimeError("Injected fault after state")
            self.pending.unlink()

    def rollback(self):
        with self.locked():
            state = self._verify_consistency()
            previous = state["previous"]
        if previous is None:
            fail("No previous release for rollback")
        self.switch(previous)

    def recover(self):
        """Journal-driven rollback after any injected partial-transaction failure."""
        with self.locked():
            if not _exists(self.pending):
                return
            if self.pending.is_symlink():
                fail("Foreign journal symlink")
            journal = json.loads(self.pending.read_text(encoding="utf-8"))
            if journal.get("owner") != OWNER:
                fail("Foreign pending journal")
            before = journal["before"]
            name = before["active"]
            if name is not None:
                self._verify_release(name)
            self._set_pointer(name)
            _write_atomic(self.state_path, _json_bytes(before))
            self.pending.unlink()
            self._verify_consistency()

    def status(self):
        with self.locked():
            state = self._verify_consistency()
            return dict(state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", required=True)
    args = parser.parse_args(argv)
    print("Flight Radar safe-preview TRANSACTION DESIGN — no installer executable")
    print("Exact original installed source: 950f8278a625ce13a9a3c7e21bf9bf76d4b5888e")
    print("Security candidate base: f923d8c1fc3333052ca3865fe68e2e9d39a73791")
    print("Fixture-only CI stages, atomic current link, journal recovery and simulated rollback.")
    print("No actual Python/Qt installation, no pipx, no sudoers change, no live SDR.")
    print("REAL INSTALL / UNINSTALL / RELEASE: HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
