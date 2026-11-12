#!/usr/bin/env python3
"""CI-only disposable Flight transaction experiment, not a production installer.

No write-capable CLI exists. Mutations require explicit CI flags, an owner-only
fixture root, and Linux descriptor-relative filesystem primitives. Environment
flags are NOT an authentication boundary against a same-UID hostile process.
No package installation, app import, services, network, or receiver operations.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

try:
    import fcntl
except ImportError:  # Windows may collect the tests, but cannot run POSIX lab.
    fcntl = None

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
OWNER = "TIHULU_FLIGHT_TRANSACTION_LAB_V1"
MAX_SIZE = 1024 * 1024
MAX_META = 4096
_DIR = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_EXCHANGE, _NOREPLACE = 2, 1


def fail(message):
    raise RuntimeError(message)


def _valid_name(name):
    return type(name) is str and NAME.fullmatch(name) is not None


def _validate_state(s):
    if (type(s) is not dict or set(s) != {"owner", "active", "previous"}
            or s["owner"] != OWNER):
        fail("Foreign or corrupt transaction state")
    for key in ("active", "previous"):
        if s[key] is not None and not _valid_name(s[key]):
            fail("Invalid state release name")
    return s


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _decode_json(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                fail("Duplicate JSON key")
            obj[k] = v
        return obj
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, ValueError, TypeError) as exc:
        fail("Invalid transaction JSON: " + str(exc)[:100])


def _inode(st):
    return (st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode))


def _owned(st, *, directory=False):
    if st.st_uid != os.getuid() or st.st_mode & 0o022:
        fail("Foreign ownership or unsafe writable mode")
    if directory and not stat.S_ISDIR(st.st_mode):
        fail("Expected owner directory")
    if not directory and (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1):
        fail("Foreign or hard-linked file")


def _fsync(fd):
    os.fsync(fd)


def _open_chain(path, *, create=False):
    """Open all components from / without ever following an intermediate link."""
    if not path.is_absolute() or ".." in path.parts:
        fail("Non-absolute or traversing fixture path")
    fd = os.open("/", _DIR)
    try:
        for i, part in enumerate(path.parts[1:]):
            last = i == len(path.parts) - 2
            try:
                child = os.open(part, _DIR, dir_fd=fd)
            except FileNotFoundError:
                if not (create and last):
                    raise
                os.mkdir(part, 0o700, dir_fd=fd)
                _fsync(fd)
                child = os.open(part, _DIR, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _dir_open(parent_fd, name, *, create=False):
    try:
        fd = os.open(name, _DIR, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        _fsync(parent_fd)
        fd = os.open(name, _DIR, dir_fd=parent_fd)
    _owned(os.fstat(fd), directory=True)
    return fd


def _entry(fd, name):
    try:
        return os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _read_file(fd, name, limit=MAX_META):
    handle = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=fd)
    try:
        _owned(os.fstat(handle))
        raw = bytearray()
        while len(raw) <= limit:
            part = os.read(handle, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        if len(raw) > limit:
            fail("Oversized transaction file")
        return bytes(raw), _inode(os.fstat(handle))
    finally:
        os.close(handle)


def _write_new(fd, name, payload):
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                     0o600, dir_fd=fd)
    try:
        _owned(os.fstat(handle))
        with os.fdopen(handle, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
        _fsync(handle)
    finally:
        os.close(handle)
    _fsync(fd)


def _rename(fd, src, dst, flag):
    """Linux renameat2: never silently overwrite an unrelated directory entry."""
    if not sys.platform.startswith("linux"):
        fail("Linux-only secure rename experiment")
    libc = ctypes.CDLL(None, use_errno=True)
    fn = getattr(libc, "renameat2", None)
    if fn is None:
        fail("renameat2 unavailable: HOLD")
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                   ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(fd, os.fsencode(src), fd, os.fsencode(dst), flag) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), dst)
    _fsync(fd)


def _replace_if_expected(fd, temp, target, old_inode, old_content=None):
    """Exchange never deletes a race-inserted foreign entry; undo on mismatch."""
    actual = _entry(fd, target)
    if old_inode is None:
        if actual is not None:
            fail("Foreign file collision")
        try:
            _rename(fd, temp, target, _NOREPLACE)
        except FileExistsError:
            fail("Foreign file collision")
        return
    if actual is None:
        fail("Protected entry unexpectedly disappeared")
    _rename(fd, temp, target, _EXCHANGE)
    try:
        displaced = _entry(fd, temp)
        if displaced is None or _inode(displaced) != old_inode:
            fail("Foreign file swapped during transaction")
        if old_content is not None:
            if stat.S_ISLNK(displaced.st_mode):
                if os.readlink(temp, dir_fd=fd) != old_content:
                    fail("Changed protected pointer")
            elif _read_file(fd, temp)[0] != old_content:
                fail("Changed protected state")
    except BaseException:
        # Exchange back, keeping foreign bytes intact; journal stays for recovery.
        try:
            _rename(fd, temp, target, _EXCHANGE)
        except BaseException:
            fail("Cannot restore raced entry; preserve recovery evidence")
        raise
    os.unlink(temp, dir_fd=fd)
    _fsync(fd)


def _atomic_file(fd, target, payload, expected_inode=None, expected_raw=None):
    temp = ".tx-" + uuid.uuid4().hex
    _write_new(fd, temp, payload)
    try:
        _replace_if_expected(fd, temp, target, expected_inode, expected_raw)
    finally:
        st = _entry(fd, temp)
        if st is not None and stat.S_ISREG(st.st_mode):
            # Never remove foreign entry after failed exchange restoration.
            if st.st_uid == os.getuid() and st.st_mode & 0o077 == 0:
                os.unlink(temp, dir_fd=fd)
                _fsync(fd)


class _View:
    """Root/release descriptors held under a single advisory transaction lock."""
    def __init__(self, root_fd, releases_fd):
        self.root_fd, self.releases_fd = root_fd, releases_fd

    def read_state(self):
        st = _entry(self.root_fd, "state.json")
        if st is None:
            return _validate_state({"owner": OWNER, "active": None, "previous": None}), None, None
        raw, ino = _read_file(self.root_fd, "state.json")
        return _validate_state(_decode_json(raw)), ino, raw

    def pointer(self):
        st = _entry(self.root_fd, "current")
        if st is None:
            return None, None, None
        if not stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid():
            fail("Foreign current entry")
        link = os.readlink("current", dir_fd=self.root_fd)
        name = link[9:] if link.startswith("releases/") else None
        if not _valid_name(name) or link != "releases/" + name:
            fail("Foreign current symlink destination")
        after = _entry(self.root_fd, "current")
        if after is None or _inode(st) != _inode(after):
            fail("Current changed during inspection")
        return name, _inode(st), link

    def verify_release(self, name):
        if not _valid_name(name):
            fail("Invalid fixture release name")
        release_fd = _dir_open(self.releases_fd, name)
        try:
            keys = sorted(os.listdir(release_fd))
            if keys != ["image.bin", "manifest.json"]:
                fail("Foreign release contents")
            raw, _ = _read_file(release_fd, "image.bin", MAX_SIZE)
            meta, _ = _read_file(release_fd, "manifest.json")
            expected = {"owner": OWNER, "name": name,
                        "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
            if not raw or _decode_json(meta) != expected:
                fail("Release manifest does not match fixture bytes")
            return expected
        finally:
            os.close(release_fd)

    def consistency(self, *, allow_pending=False):
        state, ino, raw = self.read_state()
        if not allow_pending and _entry(self.root_fd, "pending.json") is not None:
            fail("Unfinished transaction: call recover")
        current, pointer_inode, link = self.pointer()
        if current != state["active"]:
            fail("State/current pointer mismatch")
        if current is not None:
            self.verify_release(current)
        return state, ino, raw, pointer_inode, link

    def set_pointer(self, name):
        current, current_inode, link = self.pointer()
        if name is None:
            if current_inode is not None:
                # There is no safe unlink-CAS with POSIX rename alone.
                # Exchange a new tombstone file, validate displaced pointer.
                self._pointer_tombstone(current_inode, link)
            return
        if name == current:
            return
        tmp = ".pointer-" + uuid.uuid4().hex
        os.symlink("releases/" + name, tmp, dir_fd=self.root_fd)
        _fsync(self.root_fd)
        try:
            _replace_if_expected(self.root_fd, tmp, "current", current_inode, link)
        finally:
            if _entry(self.root_fd, tmp) is not None:
                # Only our own temporary symlink is safe to discard.
                if os.readlink(tmp, dir_fd=self.root_fd) == "releases/" + name:
                    os.unlink(tmp, dir_fd=self.root_fd)
                    _fsync(self.root_fd)

    def _pointer_tombstone(self, current_inode, link):
        tmp = ".tombstone-" + uuid.uuid4().hex
        _write_new(self.root_fd, tmp, b"deactivated\n")
        try:
            _replace_if_expected(self.root_fd, tmp, "current", current_inode, link)
            os.unlink("current", dir_fd=self.root_fd)
            _fsync(self.root_fd)
        finally:
            if _entry(self.root_fd, tmp) is not None:
                os.unlink(tmp, dir_fd=self.root_fd)
                _fsync(self.root_fd)

    def change(self, target, state=None):
        if state is None:
            state, old_ino, old_raw, _, _ = self.consistency()
        else:
            state, old_ino, old_raw = state
        if target is not None:
            self.verify_release(target)
        if target == state["active"]:
            return
        # Journal must be durable BEFORE pointer or state changes.
        before = state
        journal = {"owner": OWNER, "before": before, "to": target}
        _atomic_file(self.root_fd, "pending.json", _json_bytes(journal))
        return old_ino, old_raw

    def commit(self, target, before, old_ino, old_raw, fault=None):
        if fault == "after_journal":
            fail("Injected fault after journal")
        self.set_pointer(target)
        if fault == "after_pointer":
            fail("Injected fault after pointer")
        updated = {"owner": OWNER, "active": target, "previous": before["active"]}
        _atomic_file(self.root_fd, "state.json", _json_bytes(updated), old_ino, old_raw)
        if fault == "after_state":
            fail("Injected fault after state")
        self.finish(updated)

    def finish(self, expected_state):
        state, _, _, _, _ = self.consistency(allow_pending=True)
        if state != expected_state:
            fail("Consistency failed: preserve pending journal")
        # Ensure all earlier updates are durable before destroying evidence.
        _fsync(self.root_fd)
        if _entry(self.root_fd, "pending.json") is None:
            fail("Missing pending journal")
        os.unlink("pending.json", dir_fd=self.root_fd)
        _fsync(self.root_fd)


class TransactionLab:
    def __init__(self, root: Path):
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
            fail("CI-only laboratory; no workstation installation is possible")
        if not sys.platform.startswith("linux") or fcntl is None:
            fail("Linux-only POSIX transaction laboratory")
        runner = os.environ.get("RUNNER_TEMP")
        if not runner:
            fail("RUNNER_TEMP is required")
        base = Path(runner)
        root = Path(root)
        if not root.is_absolute() or not base.is_absolute() or not _valid_name(root.name):
            fail("Absolute disposable paths and names required")
        if root.parent != base / "flight-transaction-lab":
            fail("Fixture must be a direct child of RUNNER_TEMP/flight-transaction-lab")
        self.root = root
        self.releases = root / "releases"
        self.current = root / "current"
        self.state_path = root / "state.json"
        self.pending = root / "pending.json"
        self.lock_path = root / "lab.lock"
        # Reject symlinked ancestors even if the terminal path does not yet exist.
        current = Path("/")
        for part in root.parts[1:]:
            current = current / part
            if current.is_symlink():
                fail("Symlink is forbidden in path ancestors")
        if base.exists():
            _owned(base.lstat(), directory=True)

    @contextlib.contextmanager
    def locked(self):
        base = Path(os.environ["RUNNER_TEMP"])
        basefd = _open_chain(base)
        try:
            _owned(os.fstat(basefd), directory=True)
            parentfd = _dir_open(basefd, "flight-transaction-lab", create=True)
            try:
                rootfd = _dir_open(parentfd, self.root.name, create=True)
                try:
                    lockfd = os.open("lab.lock",
                        os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o600, dir_fd=rootfd)
                    try:
                        _owned(os.fstat(lockfd))
                        fcntl.flock(lockfd, fcntl.LOCK_EX)
                        st = _entry(rootfd, "lab.lock")
                        if st is None or _inode(st) != _inode(os.fstat(lockfd)):
                            fail("Lock entry replaced")
                        releasesfd = _dir_open(rootfd, "releases", create=True)
                        try:
                            yield _View(rootfd, releasesfd)
                        finally:
                            os.close(releasesfd)
                            fcntl.flock(lockfd, fcntl.LOCK_UN)
                    finally:
                        os.close(lockfd)
                finally:
                    os.close(rootfd)
            finally:
                os.close(parentfd)
        finally:
            os.close(basefd)

    def stage_fixture(self, name, payload):
        if not _valid_name(name):
            fail("Invalid fixture release name")
        if type(payload) is not bytes or not payload or len(payload) > MAX_SIZE:
            fail("Fixture size out of bounds")
        with self.locked() as view:
            if _entry(view.root_fd, "pending.json") is not None:
                fail("Pending transaction requires recover")
            if _entry(view.releases_fd, name) is not None:
                fail("Release already exists; do not overwrite")
            if any(item.startswith(".stage-") for item in os.listdir(view.releases_fd)):
                fail("Unresolved interrupted staging: preserve evidence")
            stage = ".stage-" + uuid.uuid4().hex
            stagefd = _dir_open(view.releases_fd, stage, create=True)
            try:
                _write_new(stagefd, "image.bin", payload)
                _write_new(stagefd, "manifest.json", _json_bytes({
                    "owner": OWNER, "name": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload)}))
            finally:
                os.close(stagefd)
            _rename(view.releases_fd, stage, name, _NOREPLACE)

    def switch(self, name, *, fault=None):
        if name is not None and not _valid_name(name):
            fail("Invalid switch target")
        with self.locked() as view:
            state, old_ino, old_raw, _, _ = view.consistency()
            if name == state["active"]:
                return
            view.change(name, (state, old_ino, old_raw))
            view.commit(name, state, old_ino, old_raw, fault=fault)

    def rollback(self):
        # Selection and commit are under ONE lock (not two transactions).
        with self.locked() as view:
            state, old_ino, old_raw, _, _ = view.consistency()
            target = state["previous"]
            if target is None:
                fail("No previous release for rollback")
            view.change(target, (state, old_ino, old_raw))
            view.commit(target, state, old_ino, old_raw)

    def recover(self):
        with self.locked() as view:
            if _entry(view.root_fd, "pending.json") is None:
                return
            raw, _ = _read_file(view.root_fd, "pending.json")
            journal = _decode_json(raw)
            if type(journal) is not dict or set(journal) != {"owner", "before", "to"}:
                fail("Foreign or corrupt pending journal")
            if journal["owner"] != OWNER:
                fail("Foreign pending journal")
            before = _validate_state(journal["before"])
            target = journal["to"]
            if target is not None and not _valid_name(target):
                fail("Invalid journal target")
            if before["active"] is not None:
                view.verify_release(before["active"])
            if target is not None:
                view.verify_release(target)
            state, old_ino, old_raw = view.read_state()
            original = before
            newer = {"owner": OWNER, "active": target, "previous": before["active"]}
            if state != original and state != newer:
                fail("Recovery state conflicts with journal")
            current, _, _ = view.pointer()
            if current not in (before["active"], target):
                fail("Recovery pointer conflicts with journal")
            # All validation occurs before the first mutation.
            view.set_pointer(before["active"])
            _atomic_file(view.root_fd, "state.json", _json_bytes(before),
                         old_ino, old_raw)
            view.finish(before)

    def status(self):
        with self.locked() as view:
            state, _, _, _, _ = view.consistency()
            return dict(state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", required=True)
    parser.parse_args(argv)
    print("Flight Radar CI transaction design; no executable installer")
    print("Fixture-only staging, pointer transaction, journal recovery, rollback.")
    print("Production installation, power-fail assurance and release: HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
