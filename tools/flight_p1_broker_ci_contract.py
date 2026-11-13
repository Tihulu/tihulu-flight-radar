#!/usr/bin/env python3
"""Agent 08 P1-BROKER/SAME-UID disposable Linux CI *contract model*.

NOT an operating-system security boundary, privileged service, installer,
packager, rollback agent, production authenticator, or deployment entrypoint.
ALL files live under RUNNER_TEMP; code is deliberately inert outside hosted CI.
The model reuses frozen PR42 signature verification but checks transferred FDs
again INSIDE the model, never trusting client-side "verified" Python objects.
"""
from __future__ import annotations

from contextlib import contextmanager
import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading

from tools import flight_signed_installer_ci_prototype as signed

DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
REQUIRED_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                  fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
DEFAULT_BACKGROUND = False
# EXPLICIT NON-OPERATIONS: borrowed readsb/tar1090 and other apps' SDR never
# become broker-owned resources. This model has no process or device API.


class BrokerRejected(RuntimeError):
    """Fail closed; no caller-provided path or identity can override policy."""


class SimulatedCrash(RuntimeError):
    """Intentional disposable test cut at a specified durable phase."""


def ci_only():
    if (sys.platform != "linux" or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or not os.environ.get("RUNNER_TEMP")
            or not hasattr(socket, "SCM_RIGHTS")
            or not hasattr(os, "memfd_create")):
        raise BrokerRejected("disposable Linux GitHub Actions CI required")


def reject(msg):
    raise BrokerRejected(msg)


def safe_component(name):
    if (type(name) is not str or not name or name in (".", "..")
            or "/" in name or "\x00" in name or "\\" in name
            or len(name) > 96 or not name.isascii()
            or not all(ch.isalnum() or ch in "._-" for ch in name)):
        reject("unsafe broker-controlled component")
    return name


def pinned_root(path):
    """Walk every ancestor from / with O_NOFOLLOW|O_DIRECTORY.

    An already-pinned FD survives path swaps; that does NOT anchor the public
    pathname if a same-UID writer can change its parent. Production requires
    OS-owned non-writable ancestors and a separately protected broker.
    """
    ci_only()
    path = Path(path)
    runner = Path(os.environ["RUNNER_TEMP"])
    if (not path.is_absolute() or not runner.is_absolute()
            or not path.is_relative_to(runner) or path == runner
            or any(x in (".", "..") for x in path.parts)):
        reject("CI store must be inside RUNNER_TEMP")
    root = os.open("/", DIR)
    try:
        for part in path.parts[1:]:
            nxt = os.open(safe_component(part), DIR, dir_fd=root)
            os.close(root)
            root = nxt
        return root
    except BaseException:
        os.close(root)
        raise


def child_dir(parent_fd, name):
    return os.open(safe_component(name), DIR, dir_fd=parent_fd)


def read_regular(parent_fd, name, max_len=4096):
    try:
        fd = os.open(safe_component(name), FILE_READ, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size > max_len or info.st_size < 0):
            reject("unsafe existing broker record")
        data = os.pread(fd, max_len + 1, 0)
        if len(data) != info.st_size:
            reject("broker record changed during read")
        return data
    finally:
        os.close(fd)


def json_record(raw, fields):
    if raw is None:
        return None
    try:
        obj = json.loads(raw.decode("ascii"))
        if (type(obj) is not dict or set(obj) != set(fields)
                or type(obj["seq"]) is not int or obj["seq"] < 0
                or type(obj["release"]) is not str):
            reject("corrupt broker record")
        safe_component(obj["release"])
        if "digest" in fields:
            if (type(obj["digest"]) is not str or len(obj["digest"]) != 64
                    or any(c not in "0123456789abcdef" for c in obj["digest"])
                    or obj["previous"] is not None and
                    (type(obj["previous"]) is not str or
                     not safe_component(obj["previous"]))):
                reject("corrupt journal digest/previous")
        return obj
    except (UnicodeError, ValueError, TypeError, KeyError):
        reject("corrupt broker record")


def _atomic_record(folder_fd, name, data, expected_old):
    """Caller MUST hold broker transaction lock; simulation isn't same-UID safe."""
    old = read_regular(folder_fd, name)
    if old != expected_old:
        reject("record mismatch; foreign or concurrent data preserved")
    tmp = safe_component(name + ".broker-new")
    fd = os.open(tmp, FILE_NEW, 0o600, dir_fd=folder_fd)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                reject("short broker write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    # tmp is deliberately left for forensic inspection if an error occurs.
    # Only a protected broker-owned directory makes check + rename safe.
    os.replace(tmp, name, src_dir_fd=folder_fd, dst_dir_fd=folder_fd)
    os.fsync(folder_fd)


def send_one_fd(sock, fd):
    """Local CI IPC fixture: caller's metadata is never authority."""
    ci_only()
    rights = array.array("i", [fd])
    sent = sock.sendmsg([b"F"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)])
    if sent != 1:
        reject("incomplete FD transfer")


def receive_one_fd(sock):
    """Validate SCM_RIGHTS cardinality and ask Linux for immutable peer creds."""
    ci_only()
    maxfds = 16
    msg, anc, flags, _ = sock.recvmsg(
        1, socket.CMSG_SPACE(array.array("i").itemsize * maxfds),
        getattr(socket, "MSG_CMSG_CLOEXEC", 0))
    found = []
    try:
        for level, typ, blob in anc:
            if level == socket.SOL_SOCKET and typ == socket.SCM_RIGHTS:
                values = array.array("i")
                values.frombytes(blob[:len(blob) - len(blob) % values.itemsize])
                found.extend(values)
        if (msg != b"F" or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
                or len(found) != 1):
            reject("missing, malformed or multiple transferred FDs")
        creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", creds)
        if pid <= 0 or uid < 0 or gid < 0:
            reject("invalid kernel peer credentials")
        selected = found.pop()
        return selected, (pid, uid, gid)
    finally:
        for fd in found:
            os.close(fd)


def boundary_assertion(broker_uid, client_uid):
    """A same-UID verifier must NEVER advertise an OS-enforced barrier."""
    if (type(broker_uid) is not int or type(client_uid) is not int
            or broker_uid == client_uid):
        reject("same-UID broker is not a security boundary")
    return True


def verify_received_fd(fd, metadata, signature, pinned_test_roots, *,
                       minimum_sequence, now):
    """Broker-side signature, size, seals and digest re-verification.

    Only bytes returned from THIS descriptor are staged. No source pathname,
    Python VerifiedFixture claim or client-submitted hash is trusted.
    """
    ci_only()
    signed_meta = signed.verify_metadata(
        metadata, signature, pinned_test_roots, expected_platform="linux",
        expected_arch="x86_64", minimum_sequence=minimum_sequence, now=now)
    try:
        first = os.fstat(fd)
        seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
        if (not stat.S_ISREG(first.st_mode)
                or first.st_size != signed_meta.artifact_size
                or (seals & REQUIRED_SEALS) != REQUIRED_SEALS):
            reject("unsealed, wrong-size or non-regular transferred FD")
        data = os.pread(fd, signed_meta.artifact_size + 1, 0)
        after = os.fstat(fd)
        if (len(data) != signed_meta.artifact_size
                or hashlib.sha256(data).hexdigest()
                != signed_meta.artifact_sha256
                or (first.st_dev, first.st_ino, first.st_size)
                != (after.st_dev, after.st_ino, after.st_size)
                or fcntl.fcntl(fd, fcntl.F_GET_SEALS) & REQUIRED_SEALS
                != REQUIRED_SEALS):
            reject("transferred FD changed or signed digest mismatch")
        return signed_meta, data
    except OSError:
        reject("invalid or closed artifact FD")


class DisposableBrokerStore:
    """CI-only transaction *model*, owned by SAME test UID: NOT PROTECTED.

    Production equivalent requires a distinct OS-controlled user/privilege,
    OS-owned immutable broker code/keyring and each storage ancestor.
    All namespace operations below are dirfd-relative; untrusted same-UID
    code can still mutate these CI directories outside our Python lock.
    """
    def __init__(self, root_path):
        ci_only()
        self._thread_lock = threading.Lock()
        self.root = pinned_root(root_path)
        self.dirs = {}
        try:
            for name in ("releases", "journal", "activation", "locks"):
                try:
                    os.mkdir(name, 0o700, dir_fd=self.root)
                except FileExistsError:
                    pass
                self.dirs[name] = child_dir(self.root, name)
            lock_fd = os.open("transaction.lock", FILE_NEW, 0o600,
                              dir_fd=self.dirs["locks"]) if (
                read_regular(self.dirs["locks"], "transaction.lock") is None
            ) else None
            if lock_fd is not None:
                os.close(lock_fd)
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd in self.dirs.values():
            os.close(fd)
        self.dirs.clear()
        if getattr(self, "root", None) is not None:
            os.close(self.root)
            self.root = None

    @contextmanager
    def transaction(self):
        if not self._thread_lock.acquire(blocking=False):
            reject("broker already servicing a transaction")
        fd = None
        try:
            fd = os.open("transaction.lock", os.O_RDWR | os.O_NOFOLLOW |
                         os.O_CLOEXEC, dir_fd=self.dirs["locks"])
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                reject("untrusted broker transaction lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                reject("concurrent broker transaction")
            yield
        finally:
            if fd is not None:
                os.close(fd)
            self._thread_lock.release()

    def state(self):
        raw = read_regular(self.dirs["journal"], "current.json")
        return raw, json_record(raw, ("seq", "release", "digest", "previous"))

    def pointer(self):
        raw = read_regular(self.dirs["activation"], "active.json")
        return raw, json_record(raw, ("seq", "release"))

    def _assert_pointer(self, state, pointer):
        if state is None:
            if pointer is not None:
                reject("foreign activation pointer, preserve it")
        elif (pointer is None or pointer["seq"] != state["seq"]
              or pointer["release"] != state["release"]):
            reject("activation doesn't match broker journal; recover first")

    def install(self, signed_meta, data, *, cut=None):
        """One CI blob per signed release; NO unpack, launcher or elevation."""
        ci_only()
        if (type(data) is not bytes or
                hashlib.sha256(data).hexdigest() != signed_meta.artifact_sha256
                or len(data) != signed_meta.artifact_size):
            reject("unsigned content passed to broker store")
        with self.transaction():
            oldraw, old = self.state()
            _, current = self.pointer()
            self._assert_pointer(old, current)
            if old and signed_meta.sequence <= old["seq"]:
                reject("replay or rollback requires independent approval")
            release = safe_component(
                "rel-" + str(signed_meta.sequence) + "-" +
                signed_meta.artifact_sha256[:24] + ".bin")
            fd = os.open(release, FILE_NEW, 0o600, dir_fd=self.dirs["releases"])
            try:
                view = memoryview(data)
                while view:
                    n = os.write(fd, view)
                    if n <= 0:
                        reject("short release write")
                    view = view[n:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(self.dirs["releases"])
            if cut == "after_release":
                raise SimulatedCrash("durable release before journal")
            new = dict(seq=signed_meta.sequence, release=release,
                       digest=signed_meta.artifact_sha256,
                       previous=None if old is None else old["release"])
            payload = json.dumps(new, sort_keys=True, separators=(",", ":")).encode()
            _atomic_record(self.dirs["journal"], "current.json", payload, oldraw)
            if cut == "after_journal":
                raise SimulatedCrash("journal committed, activation pending")
            self._publish_pointer(new, old)
            return release

    def _publish_pointer(self, new, previous):
        raw, pointer = self.pointer()
        if previous is None:
            if pointer is not None:
                reject("foreign activation pointer; preserve")
        else:
            if pointer and (pointer["seq"] != previous["seq"]
                            or pointer["release"] != previous["release"]):
                reject("unexpected pointer during transition")
            if pointer is None:
                reject("missing prior pointer")
        payload = json.dumps({"seq":new["seq"],"release":new["release"]},
                             sort_keys=True, separators=(",", ":")).encode()
        _atomic_record(self.dirs["activation"], "active.json", payload, raw)

    def recover(self):
        """Recover only journal-committed transaction. No destructive cleanup."""
        with self.transaction():
            _, state = self.state()
            if state is None:
                return False
            raw = read_regular(self.dirs["releases"], state["release"],
                               max_len=signed.MAX_ARTIFACT)
            if raw is None or hashlib.sha256(raw).hexdigest() != state["digest"]:
                reject("journal points to missing/modified release; HOLD")
            _, pointer = self.pointer()
            if (pointer is not None and pointer["seq"] == state["seq"]
                    and pointer["release"] == state["release"]):
                return True
            if (state["previous"] is None and pointer is not None
                    or state["previous"] is not None and
                    (pointer is None or
                     pointer["release"] != state["previous"])):
                reject("unrecognized rollback/pointer, preserve and HOLD")
            self._publish_pointer(state, None if state["previous"] is None
                                  else pointer)
            return True

    def rollback(self, *_args, **_kwargs):
        reject("rollback authorization and signed safety ticket not implemented")
