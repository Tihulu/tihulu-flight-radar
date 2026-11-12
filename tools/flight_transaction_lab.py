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
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from types import MappingProxyType

try:
    import fcntl
except ImportError:  # Windows may collect the tests, but cannot run POSIX lab.
    fcntl = None

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
OWNER = "TIHULU_FLIGHT_TRANSACTION_LAB_V1"
MAX_SIZE = 1024 * 1024
MAX_META = 4096
RETAINED_MAX = 256  # Cooperative synthetic lab bound only; never auto-delete.
RETAINED_RESERVE = 4  # Conservative worst-case entries in one transaction.
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


def _retained_count(fd):
    return sum(name.startswith((".tx-", ".pointer-", ".retired-"))
               for name in os.listdir(fd))


def _reserve_retained(fd, slots=1):
    # Caller must hold the cooperative transaction lock. An adversarial
    # same-UID process can add entries without that lock: not a hard cap
    # against a hostile mutable namespace.
    if slots < 0 or _retained_count(fd) + slots > RETAINED_MAX:
        fail("Retained transaction evidence limit exceeded: manual review")


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
        created_inode = _inode(os.fstat(handle))
        with os.fdopen(handle, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
        _fsync(handle)
    finally:
        os.close(handle)
    _fsync(fd)
    return created_inode


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
    # The displaced entry stays at 'temp' as durable quarantine evidence.
    # There is NO safe path-based unlink-if-inode-matches on a directory
    # writable by a hostile same-UID actor. Do not "check then unlink".
    # A later trusted owner must inspect and clean these entries manually.
    _fsync(fd)


def _atomic_file(fd, target, payload, expected_inode=None, expected_raw=None):
    _reserve_retained(fd)
    temp = ".tx-" + uuid.uuid4().hex
    _write_new(fd, temp, payload)
    # Failed attempts also leave temp in place: manual inspection, no auto
    # cleanup that could delete a foreign entry after a final inode check.
    _replace_if_expected(fd, temp, target, expected_inode, expected_raw)


class _View:
    """Root/release descriptors held under a single advisory transaction lock."""
    def __init__(self, root_fd, releases_fd, external_pins=None):
        self.root_fd, self.releases_fd = root_fd, releases_fd
        self.external_pins = external_pins
        self.pending_proof = None
        # Bytes come from the SAME read that passed manifest and external pin
        # checks. They are an immutable in-process snapshot, never a path to
        # reopen later. This is NOT a signed or production artifact handoff.
        self.verified_snapshots = {}

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
            if self.external_pins is not None:
                # An out-of-tree, independently trusted digest is different
                # from the publicly forgeable *in-release* self-hash. This
                # only checks a caller-provided pin: it is NOT authentication
                # of the pin's origin, of the caller, or a release signature.
                pin = self.external_pins.get(name)
                if pin is None or not hmac.compare_digest(pin, expected["sha256"]):
                    fail("Externally pinned artifact digest mismatch: HOLD")
            validated = bytes(raw)
            prior = self.verified_snapshots.get(name)
            if prior is not None and prior != validated:
                fail("Verified fixture bytes changed after validation: HOLD")
            self.verified_snapshots[name] = validated
            return expected
        finally:
            os.close(release_fd)

    def verified_bytes(self, name):
        """Return only bytes previously read and checked under this view.

        Never return an unverified path or reopen image.bin for installation.
        A production counterpart would use sealed memfd/FD handoff and verify
        actual signatures from a trusted keyring, NOT this CI-only bytes API.
        """
        try:
            return self.verified_snapshots[name]
        except KeyError:
            fail("No validated byte snapshot for requested release")

    def check_verified_snapshots(self):
        """Fail closed if any source changed between initial check and exit.

        A hostile same-UID actor can mutate after this last check or restore
        bytes before it; that is a permanent threat-model HOLD. Independent
        byte snapshots remain intact for a future sealed-FD handoff design.
        """
        for name, original_bytes in tuple(self.verified_snapshots.items()):
            self.verify_release(name)
            if self.verified_snapshots[name] != original_bytes:
                fail("Verified fixture bytes changed after validation: HOLD")

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
                self._pointer_deactivate(current_inode, link)
            return
        if name == current:
            return
        _reserve_retained(self.root_fd)
        tmp = ".pointer-" + uuid.uuid4().hex
        os.symlink("releases/" + name, tmp, dir_fd=self.root_fd)
        _fsync(self.root_fd)
        # Every failed or displaced pointer is retained; never path-unlink a
        # writable namespace entry after verifying an earlier inode.
        _replace_if_expected(self.root_fd, tmp, "current", current_inode, link)

    def _pointer_deactivate(self, current_inode, link):
        # Rename the old pointer to a unique retired name. If a foreign entry
        # appeared, it is never destroyed: failed verification restores it.
        _reserve_retained(self.root_fd)
        retired = ".retired-" + uuid.uuid4().hex
        _rename(self.root_fd, "current", retired, _NOREPLACE)
        displaced = _entry(self.root_fd, retired)
        if (displaced is None or _inode(displaced) != current_inode
                or not stat.S_ISLNK(displaced.st_mode)
                or os.readlink(retired, dir_fd=self.root_fd) != link):
            try:
                _rename(self.root_fd, retired, "current", _NOREPLACE)
            except BaseException:
                fail("Raced entry preserved in retired slot; recovery HOLD")
            fail("Foreign pointer raced during deactivation")
        # Retain verified former pointer for owner inspection; no unlink race.
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
        # Never silently purge retained evidence. Cap the number of retained
        # slots so CI cannot write an unbounded history without manual review.
        _reserve_retained(self.root_fd, RETAINED_RESERVE)
        # Journal must be durable BEFORE pointer or state changes.
        before = state
        journal = {"owner": OWNER, "before": before, "to": target}
        payload = _json_bytes(journal)
        _atomic_file(self.root_fd, "pending.json", payload)
        actual, inode = _read_file(self.root_fd, "pending.json")
        if actual != payload:
            fail("Pending journal changed after creation")
        self.pending_proof = (inode, actual)
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
        if self.pending_proof is None:
            fail("Missing trusted journal proof")
        original_inode, original_bytes = self.pending_proof
        raw, inode = _read_file(self.root_fd, "pending.json")
        if (inode, raw) != (original_inode, original_bytes):
            fail("Pending journal was replaced: preserve evidence")
        _fsync(self.root_fd)
        _reserve_retained(self.root_fd)
        retired = ".retired-journal-" + uuid.uuid4().hex
        _rename(self.root_fd, "pending.json", retired, _NOREPLACE)
        displaced, after_inode = _read_file(self.root_fd, retired)
        if (after_inode, displaced) != (original_inode, original_bytes):
            try:
                _rename(self.root_fd, retired, "pending.json", _NOREPLACE)
            except BaseException:
                fail("Raced journal preserved in retired slot; HOLD")
            fail("Foreign journal raced finalization")
        # Keep the checked committed journal in a retired quarantine slot.
        # Its bytes remain available even if later forensic inspection is needed.
        _fsync(self.root_fd)


class TransactionLab:
    def __init__(self, root: Path, *, external_pins=None):
        # external_pins are supplied by a separately trusted caller in
        # disposable tests, NEVER read from the mutable release root.
        # They do not imply a verified signer or supply-chain authenticity.
        if external_pins is not None:
            if type(external_pins) is not dict or any(
                not _valid_name(name) or type(digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                for name, digest in external_pins.items()
            ):
                fail("Invalid externally pinned digest registry")
        self._external_pins = (None if external_pins is None
                               else MappingProxyType(dict(external_pins)))
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
        self._base = base  # Constructor-validated path; never read env to locate writes.
        self._base_inode = None
        self._root_inode = None
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
        if not base.exists():
            fail("Runner base missing")
        _owned(base.lstat(), directory=True)
        self._base_inode = _inode(base.lstat())
        if root.exists():
            _owned(root.lstat(), directory=True)
            self._root_inode = _inode(root.lstat())

    @contextlib.contextmanager
    def locked(self):
        # Cooperation anchor: "/" is root-owned and is not the mutable,
        # user-owned RUNNER_TEMP inode. A flock on it serializes lab clients
        # even when an attacker swaps RUNNER_TEMP and creates a second base.
        # Advisory locks cannot stop noncooperating hostile same-UID writes.
        # Do not carry this global lock into any production installer.
        if os.environ.get("RUNNER_TEMP") != os.fspath(self._base):
            fail("RUNNER_TEMP changed after fixture construction")
        namespace_fd = os.open("/", _DIR)
        try:
            fcntl.flock(namespace_fd, fcntl.LOCK_EX)
            try:
                basefd = _open_chain(self._base)
                try:
                    _owned(os.fstat(basefd), directory=True)
                    if _inode(os.fstat(basefd)) != self._base_inode:
                        fail("Validated runner base inode changed")
                    fcntl.flock(basefd, fcntl.LOCK_EX)
                    try:
                        parentfd = _dir_open(
                            basefd, "flight-transaction-lab", create=True)
                        try:
                            rootfd = _dir_open(
                                parentfd, self.root.name, create=True)
                            try:
                                root_identity = _inode(os.fstat(rootfd))
                                if self._root_inode is None:
                                    self._root_inode = root_identity
                                elif root_identity != self._root_inode:
                                    fail("Fixture root inode changed")

                                def check_namespace():
                                    # Two independently reopened path walks,
                                    # not just a stale name resolved ONCE.
                                    # This catches swaps injected after the
                                    # first _open_chain returned its FD. Still
                                    # not an atomic snapshot or a guarantee
                                    # against a hostile same-UID actor.
                                    for _round in range(2):
                                        try:
                                            live_base = _open_chain(self._base)
                                            try:
                                                if _inode(os.fstat(live_base)) != self._base_inode:
                                                    fail("Validated runner base namespace changed during transaction")
                                                live_parent = _dir_open(
                                                    live_base, "flight-transaction-lab")
                                                try:
                                                    if _inode(os.fstat(live_parent)) != _inode(os.fstat(parentfd)):
                                                        fail("Fixture parent namespace changed during transaction")
                                                    live_root = _dir_open(live_parent, self.root.name)
                                                    try:
                                                        if _inode(os.fstat(live_root)) != root_identity:
                                                            fail("Fixture root namespace changed during transaction")
                                                    finally:
                                                        os.close(live_root)
                                                finally:
                                                    os.close(live_parent)
                                            finally:
                                                os.close(live_base)
                                        except (OSError, RuntimeError) as exc:
                                            if isinstance(exc, RuntimeError) and (
                                                "Fixture parent namespace changed" in str(exc)
                                                or "Fixture root namespace changed" in str(exc)
                                            ):
                                                raise
                                            fail("Validated runner base namespace changed during transaction")
                                    # Also compare identities under held parent
                                    # descriptor; do not trust a detached root.
                                    parent_entry = _entry(
                                        basefd, "flight-transaction-lab")
                                    if (parent_entry is None or
                                            _inode(parent_entry) != _inode(os.fstat(parentfd))):
                                        fail("Fixture parent namespace changed during transaction")
                                    root_entry = _entry(parentfd, self.root.name)
                                    if (root_entry is None or
                                            _inode(root_entry) != root_identity):
                                        fail("Fixture root namespace changed during transaction")

                                lockfd = os.open("lab.lock",
                                    os.O_RDWR | os.O_CREAT | _NOFOLLOW,
                                    0o600, dir_fd=rootfd)
                                try:
                                    _owned(os.fstat(lockfd))
                                    fcntl.flock(lockfd, fcntl.LOCK_EX)
                                    try:
                                        lockstat = _entry(rootfd, "lab.lock")
                                        if (lockstat is None or
                                                _inode(lockstat) != _inode(os.fstat(lockfd))):
                                            fail("Lock entry replaced")
                                        releasesfd = _dir_open(
                                            rootfd, "releases", create=True)
                                        try:
                                            check_namespace()
                                            view = _View(rootfd, releasesfd,
                                                         self._external_pins)
                                            try:
                                                yield view
                                            finally:
                                                # A source swapped AFTER
                                                # _View.finish must not be
                                                # silently reported as valid.
                                                # The immutable snapshot was
                                                # captured at first verification.
                                                try:
                                                    view.check_verified_snapshots()
                                                finally:
                                                    check_namespace()
                                        finally:
                                            os.close(releasesfd)
                                            final = _entry(rootfd, "lab.lock")
                                            if (final is None or
                                                    _inode(final) != _inode(os.fstat(lockfd))):
                                                fail("Lock entry replaced during transaction")
                                    finally:
                                        fcntl.flock(lockfd, fcntl.LOCK_UN)
                                finally:
                                    os.close(lockfd)
                            finally:
                                os.close(rootfd)
                        finally:
                            os.close(parentfd)
                    finally:
                        fcntl.flock(basefd, fcntl.LOCK_UN)
                finally:
                    os.close(basefd)
            finally:
                fcntl.flock(namespace_fd, fcntl.LOCK_UN)
        finally:
            os.close(namespace_fd)

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
            raw, journal_inode = _read_file(view.root_fd, "pending.json")
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
            # Recovery can also retain pointer/state/journal entries.
            # Fail before mutating if evidence headroom is insufficient.
            _reserve_retained(view.root_fd, RETAINED_RESERVE)
            # All validation occurs before the first mutation.
            view.pending_proof = (journal_inode, raw)
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
