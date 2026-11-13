#!/usr/bin/env python3
"""Agent 08: disposable ROOT-vs-unprivileged Linux broker acceptance harness.

NOT production code. Invoked only in GitHub-hosted disposable CI as a
temporary root subprocess. Never installed, systemd/sudoers/polkit modified,
or used with the owner's machine. Real UID separation + kernel DAC is
exercised; operation signatures and state use test-only keys.
"""
from __future__ import annotations

import array
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from tools import flight_signed_installer_ci_prototype as signed

DOMAIN = b"TIHULU_FLIGHT_BROKER_OPERATION_CI_V1\0"
REQUIRED_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                  fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
D = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
R = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
W = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
HEX = re.compile(r"[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
RELEASE = re.compile(r"rel-[0-9]{20}-[0-9a-f]{16}[.]bin\Z")
COMMIT = re.compile(r"txn-[0-9]{20}[.]json\Z")
FIELDS = frozenset(("schema", "op", "app_id", "channel", "sequence", "digest",
                    "previous_seq", "previous_digest", "nonce", "not_before",
                    "expires_at"))
CI_NOW = 1800000000  # SYNTHETIC! no production clock/freshness proof


class Denied(RuntimeError):
    pass


class Cut(RuntimeError):
    pass


def reject(msg):
    raise Denied(msg)


def guard():
    if (sys.platform != "linux" or os.geteuid() != 0
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("CI") != "true"
            or not os.environ.get("RUNNER_TEMP")):
        reject("disposable GitHub-hosted root-only harness required")


def canonical(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            reject("duplicate record field")
        out[k] = v
    return out


def parse(data):
    if type(data) is not bytes or not data or len(data) > 16384:
        reject("invalid record size")
    try:
        value = json.loads(data.decode("ascii"), object_pairs_hook=unique)
        if type(value) is not dict or canonical(value) != data:
            reject("noncanonical JSON")
        return value
    except (UnicodeError, TypeError, ValueError, OverflowError):
        reject("invalid JSON")


def owned(fd, *, directory=False, public=False):
    info = os.fstat(fd)
    if info.st_uid != 0 or info.st_mode & 0o022:
        reject("broker file or directory is not root-controlled")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            reject("broker directory not regular directory")
    elif (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
          or info.st_size > 1024 * 1024):
        reject("broker record not safe regular file")
    if not public and directory and info.st_mode & 0o077:
        reject("private broker directory readable by others")
    return info


def open_dir(parent, name):
    if not name or "/" in name or name in (".", ".."):
        reject("invalid directory component")
    fd = os.open(name, D, dir_fd=parent)
    owned(fd, directory=True)
    return fd


def read_file(dirfd, name, *, maximum=1024 * 1024):
    try:
        fd = os.open(name, R, dir_fd=dirfd)
    except FileNotFoundError:
        return None
    try:
        info = owned(fd)
        if info.st_size > maximum:
            reject("broker file over limit")
        raw = os.pread(fd, maximum + 1, 0)
        if len(raw) != info.st_size:
            reject("broker record changed during read")
        return raw
    finally:
        os.close(fd)


def write_new(dirfd, name, raw):
    fd = os.open(name, W, 0o600, dir_fd=dirfd)
    try:
        pos = 0
        while pos < len(raw):
            n = os.write(fd, raw[pos:])
            if n <= 0:
                reject("short broker write")
            pos += n
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(dirfd)


class Broker:
    """ROOT-only, root-owned, FD-pinned test broker core; no arbitrary paths.

    The temporary root is /tmp/flight-agent08-* owned by root, protected by
    /tmp's root-owned sticky bit. Private store is root:root 0700.
    Production requires system-owned non-user-writable *all* ancestors.
    """
    def __init__(self, root_path):
        guard()
        root_path = Path(root_path)
        if (root_path.parent != Path("/tmp")
                or not root_path.name.startswith("flight-agent08-")
                or "/" in root_path.name or root_path.is_symlink()):
            reject("invalid test-only protected root")
        self.root = None
        self.dirs = {}
        self.secret = None
        try:
            tmp = os.open("/tmp", D)
            try:
                ti = os.fstat(tmp)
                if ti.st_uid != 0 or not ti.st_mode & stat.S_ISVTX:
                    reject("/tmp sticky parent not root-owned")
                self.root = os.open(root_path.name, D, dir_fd=tmp)
            finally:
                os.close(tmp)
            owned(self.root, directory=True, public=True)
            if os.fstat(self.root).st_mode & 0o066:
                reject("public broker socket parent must not be writable")
            private = open_dir(self.root, "private")
            self.dirs["private"] = private
            for n in ("release", "journal", "active", "lock", "trust"):
                self.dirs[n] = open_dir(private, n)
            self.secret = read_file(self.dirs["trust"], "ledger.key", maximum=64)
            if self.secret is None or len(self.secret) != 32:
                reject("missing protected ledger key")
            config = read_file(self.dirs["trust"], "pins.json", maximum=4096)
            policy = parse(config) if config else None
            if (type(policy) is not dict or set(policy) != {"release", "operation"}
                    or set(policy["release"]) != {"test-root"}):
                reject("invalid independently provisioned test pins")
            self.release_pins = {"test-root": bytes.fromhex(policy["release"]["test-root"])}
            self.operation_pin = bytes.fromhex(policy["operation"])
            if (len(self.release_pins["test-root"]) != 32
                    or len(self.operation_pin) != 32):
                reject("invalid protected signing pins")
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd in self.dirs.values():
            os.close(fd)
        self.dirs.clear()
        if self.root is not None:
            os.close(self.root)
            self.root = None

    @contextmanager
    def lock(self):
        fd = os.open("transaction.lock", os.O_RDWR | os.O_NOFOLLOW |
                     os.O_CLOEXEC, dir_fd=self.dirs["lock"])
        try:
            owned(fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def mac(self, record):
        return hmac.new(self.secret, canonical(record), hashlib.sha256).hexdigest()

    def signed_record(self, record):
        return canonical({**record, "mac": self.mac(record)})

    def verify_record(self, raw, expected_fields):
        record = parse(raw)
        if set(record) != set(expected_fields) | {"mac"}:
            reject("unexpected broker record schema")
        mac = record.pop("mac")
        if (type(mac) is not str or not HEX.fullmatch(mac)
                or not hmac.compare_digest(mac, self.mac(record))):
            reject("unauthenticated broker journal/activation")
        return record

    def commits(self):
        """Validate every committed immutable journal link + release bytes."""
        records = []
        previous = None
        seen = set()
        names = sorted(os.listdir(self.dirs["journal"]))
        for name in names:
            if not COMMIT.fullmatch(name):
                reject("foreign/unrecognized broker journal entry: HOLD")
            raw = read_file(self.dirs["journal"], name, maximum=4096)
            item = self.verify_record(raw, (
                "seq", "release", "digest", "previous_seq", "previous_digest",
                "nonce", "manifest_hash", "ticket_hash"))
            if (type(item["seq"]) is not int or item["seq"] < 0 or
                    name != "txn-%020d.json" % item["seq"] or
                    type(item["release"]) is not str or
                    not RELEASE.fullmatch(item["release"]) or
                    any(type(item[k]) is not str or not HEX.fullmatch(item[k])
                        for k in ("digest", "manifest_hash", "ticket_hash")) or
                    type(item["nonce"]) is not str or
                    not NONCE.fullmatch(item["nonce"]) or
                    item["nonce"] in seen):
                reject("invalid commit data or nonce replay")
            if previous is None:
                if item["previous_seq"] is not None or item["previous_digest"] is not None:
                    reject("invalid initial journal lineage")
            elif (item["seq"] <= previous["seq"] or
                  item["previous_seq"] != previous["seq"] or
                  item["previous_digest"] != previous["digest"]):
                reject("invalid monotonic journal lineage")
            rawblob = read_file(self.dirs["release"], item["release"])
            if rawblob is None or hashlib.sha256(rawblob).hexdigest() != item["digest"]:
                reject("journal references missing/unsigned modified broker blob")
            seen.add(item["nonce"])
            records.append(item)
            previous = item
        return records

    def active(self):
        raw = read_file(self.dirs["active"], "active.json", maximum=4096)
        if raw is None:
            return None
        obj = self.verify_record(raw, ("seq", "release", "digest"))
        if (type(obj["seq"]) is not int or type(obj["release"]) is not str or
                not RELEASE.fullmatch(obj["release"]) or
                type(obj["digest"]) is not str or not HEX.fullmatch(obj["digest"])):
            reject("invalid authenticated activation")
        return obj

    def publish(self, entry):
        """Only root-owned namespace: atomic switch; never accept foreign pointer."""
        record = {k:entry[k] for k in ("seq", "release", "digest")}
        # Random, exclusive broker-owned temporary name lets fresh restart
        # recover even if a crash left an earlier, uncommitted temp file.
        # Never delete unknown or orphaned data automatically.
        name = "next-%020d-%s.tmp" % (entry["seq"], secrets.token_hex(12))
        write_new(self.dirs["active"], name, self.signed_record(record))
        # os.replace is safe against ordinary SAME-UID attacker ONLY because
        # all directory/ancestor write and rename authority belongs to root.
        os.replace(name, "active.json", src_dir_fd=self.dirs["active"],
                   dst_dir_fd=self.dirs["active"])
        os.fsync(self.dirs["active"])

    def reconcile(self, entries):
        """Replay only the authenticated committed step after a crash."""
        current = self.active()
        if not entries:
            if current is not None:
                reject("activation without committed authenticated journal")
            return None
        newest = entries[-1]
        if current and current == {k:newest[k] for k in ("seq","release","digest")}:
            return newest
        previous = entries[-2] if len(entries) > 1 else None
        if previous is None and current is not None:
            reject("foreign activation record not overwritten")
        if previous is not None and (current is None or
                current != {k:previous[k] for k in ("seq","release","digest")}):
            reject("unexpected activation predecessor: HOLD")
        self.publish(newest)
        return newest

    def recover(self):
        """Called from trusted broker process; unprivileged client cannot invoke."""
        with self.lock():
            entries = self.commits()
            current = self.reconcile(entries)
            return current["seq"] if current is not None else None

    def authorize(self, raw, signature, meta, previous, *, now):
        ticket = parse(raw)
        if set(ticket) != FIELDS:
            reject("wrong operation authorization schema")
        if (len(signature) != 64 or type(ticket["schema"]) is not int or
                ticket["schema"] != 1 or ticket["op"] != "activate" or
                ticket["app_id"] != signed.APP_ID or
                ticket["channel"] != signed.CHANNEL or
                type(ticket["sequence"]) is not int or
                ticket["sequence"] != meta.sequence or
                ticket["digest"] != meta.artifact_sha256 or
                type(ticket["nonce"]) is not str or
                not NONCE.fullmatch(ticket["nonce"]) or
                type(ticket["not_before"]) is not int or
                type(ticket["expires_at"]) is not int or
                ticket["not_before"] > now or
                ticket["expires_at"] < now or
                ticket["expires_at"] - ticket["not_before"] > 300):
            reject("per-operation authorization mismatch/expired")
        if (ticket["previous_seq"] !=
                (previous["seq"] if previous else None)
                or ticket["previous_digest"] !=
                (previous["digest"] if previous else None)):
            reject("expected protected previous activation mismatch")
        try:
            Ed25519PublicKey.from_public_bytes(self.operation_pin).verify(
                signature, DOMAIN + raw)
        except (InvalidSignature, ValueError):
            reject("independent operation signer rejected")
        return ticket

    def verify_fd(self, fd, meta):
        try:
            before = os.fstat(fd)
            seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
            if (not stat.S_ISREG(before.st_mode) or
                    before.st_size != meta.artifact_size or
                    (seals & REQUIRED_SEALS) != REQUIRED_SEALS):
                reject("unsafe or unsealed transferred artifact")
            raw = os.pread(fd, meta.artifact_size + 1, 0)
            after = os.fstat(fd)
            if (len(raw) != meta.artifact_size or
                    hashlib.sha256(raw).hexdigest() != meta.artifact_sha256 or
                    (before.st_dev, before.st_ino, before.st_size) !=
                    (after.st_dev, after.st_ino, after.st_size) or
                    fcntl.fcntl(fd, fcntl.F_GET_SEALS) & REQUIRED_SEALS
                    != REQUIRED_SEALS):
                reject("FD digest/seals/identity rejected by trusted broker")
            return raw
        except OSError:
            reject("invalid received FD")

    def activate(self, fd, manifest, release_sig, ticket, ticket_sig, *, now, cut=None):
        """Signature checks + nonce/sequence under ROOT-ONLY transaction lock."""
        with self.lock():
            entries = self.commits()
            previous = self.reconcile(entries)
            meta = signed.verify_metadata(
                manifest, release_sig, self.release_pins,
                expected_platform="linux", expected_arch="x86_64",
                minimum_sequence=0 if previous is None else previous["seq"] + 1,
                now=now)
            auth = self.authorize(ticket, ticket_sig, meta, previous, now=now)
            if any(r["nonce"] == auth["nonce"] for r in entries):
                reject("already consumed operation nonce")
            raw = self.verify_fd(fd, meta)
            release = "rel-%020d-%s.bin" % (meta.sequence, meta.artifact_sha256[:16])
            write_new(self.dirs["release"], release, raw)
            if cut == "after_release":
                raise Cut("after release fsync; old pointer remains unchanged")
            commit = {
                "seq": meta.sequence, "release": release,
                "digest": meta.artifact_sha256,
                "previous_seq": previous["seq"] if previous else None,
                "previous_digest": previous["digest"] if previous else None,
                "nonce": auth["nonce"],
                "manifest_hash": hashlib.sha256(manifest).hexdigest(),
                "ticket_hash": hashlib.sha256(ticket).hexdigest()}
            write_new(self.dirs["journal"],
                      "txn-%020d.json" % meta.sequence, self.signed_record(commit))
            if cut == "after_journal":
                raise Cut("after authenticated journal fsync; replay pending")
            self.publish(commit)
            return {"seq": meta.sequence, "release": release,
                    "digest": meta.artifact_sha256}


def provision(root_path, release_public, operation_public):
    """TEST-ONLY root provisioning. Key material never supplied by client."""
    guard()
    if len(release_public) != 32 or len(operation_public) != 32:
        reject("invalid test public key")
    root = Path(root_path)
    if (root.parent != Path("/tmp") or
            not root.name.startswith("flight-agent08-")):
        reject("unsafe root provisioning path")
    if root.is_symlink() or root.stat().st_uid != 0:
        reject("test root must be owned by root")
    os.chmod(root, 0o711)
    rootfd = os.open(root, D)
    try:
        for name in ("private",):
            os.mkdir(name, 0o700, dir_fd=rootfd)
        private = os.open("private", D, dir_fd=rootfd)
        try:
            for name in ("release", "journal", "active", "lock", "trust"):
                os.mkdir(name, 0o700, dir_fd=private)
            trust = os.open("trust", D, dir_fd=private)
            locks = os.open("lock", D, dir_fd=private)
            try:
                write_new(trust, "ledger.key", secrets.token_bytes(32))
                write_new(trust, "pins.json", canonical({
                    "release":{"test-root":release_public.hex()},
                    "operation":operation_public.hex()}))
                write_new(locks, "transaction.lock", b"")
            finally:
                os.close(trust)
                os.close(locks)
        finally:
            os.close(private)
    finally:
        os.close(rootfd)


def receive(sock):
    """Atomic seqpacket frame + one genuine SCM_RIGHTS artifact."""
    msg, anc, flags, _ = sock.recvmsg(16384,
        socket.CMSG_SPACE(array.array("i").itemsize * 16),
        socket.MSG_CMSG_CLOEXEC)
    fds = []
    try:
        for lvl, typ, raw in anc:
            if (lvl, typ) == (socket.SOL_SOCKET, socket.SCM_RIGHTS):
                ar = array.array("i")
                ar.frombytes(raw[:len(raw) - len(raw) % ar.itemsize])
                fds.extend(ar)
        if (flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or
                len(fds) != 1):
            reject("request missing/multiple/truncated artifact FD")
        payload = parse(msg)
        if set(payload) != {"metadata", "release_sig", "ticket", "ticket_sig"}:
            reject("unexpected request frame")
        def decode(k):
            try:
                return base64.b64decode(payload[k], validate=True)
            except (ValueError, TypeError):
                reject("invalid binary request field")
        peer = struct.unpack("3i", sock.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        # peercreds are ONLY channel telemetry, never an authorization ticket.
        # Decode before releasing ownership of the received descriptor.
        # On malformed frame the finally handler closes all received FDs.
        fields = tuple(decode(k) for k in
            ("metadata", "release_sig", "ticket", "ticket_sig"))
        selected = fds.pop()
        return selected, fields, peer
    finally:
        for f in fds:
            os.close(f)


def server(root_path):
    """Ephemeral root test process, Unix socket only, no installed service."""
    guard()
    b = Broker(root_path)
    b.recover()  # trusted start-up recovery only; never unprivileged IPC
    path = str(Path(root_path) / "broker.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        s.bind(path)
        os.chmod(path, 0o666)
        s.listen(6)
        print("READY", flush=True)
        while True:
            conn, _ = s.accept()
            with conn:
                # Prevent an ordinary peer from hanging this test broker
                # indefinitely by connecting without submitting a frame.
                # Production still needs quotas, rate limits and auditing.
                conn.settimeout(3)
                fd = None
                try:
                    fd, fields, peer = receive(conn)
                    result = b.activate(fd, *fields, now=CI_NOW)
                    reply = {"ok":True, "result":result,
                             "peer_uid":peer[1]}  # not a grant
                except Exception as exc:
                    reply = {"ok":False, "error":str(exc)[:200]}
                finally:
                    if fd is not None:
                        os.close(fd)
                conn.sendall(canonical(reply))
    finally:
        s.close()
        b.close()


def client(sock_path, frame_path, artifact_path):
    """Unprivileged standalone exec, never inherits harness signing keys."""
    data = Path(artifact_path).read_bytes()
    frame = Path(frame_path).read_bytes()
    fd = os.memfd_create("flight-agent08-unprivileged",
                         os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.write(fd, data)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, REQUIRED_SEALS)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        with sock:
            sock.settimeout(8)
            sock.connect(sock_path)
            sock.sendmsg([frame], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                    array.array("i", [fd]))])
            response = sock.recv(4096)
        print(response.decode("ascii"), flush=True)
    finally:
        os.close(fd)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "server":
        server(sys.argv[2])
    elif len(sys.argv) == 5 and sys.argv[1] == "client":
        client(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit("CI-only server <root> | client <socket> <frame> <blob>")
