#!/usr/bin/env python3
"""Agent08 PR52 remediation: CI-ONLY separated-UID, root-approved broker v2.

New, isolated reference implementation; frozen v1 positive vulnerability tests
remain unmodified. No OS consent daemon, production root, installer or service.
Authorizations are approved only by a separate ROOT test authority API, never
by public IPC. A stolen signed bearer ticket alone always fails closed.
"""
from __future__ import annotations

import array
import base64
import fcntl
import hashlib
import os
from pathlib import Path
import secrets
import socket
import stat
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from tools import flight_p1_broker_os_boundary_ci as old
from tools import flight_signed_installer_ci_prototype as signed

DOMAIN = b"TIHULU_FLIGHT_BROKER_OPERATION_CI_V2\0"
APPROVAL_FIELDS = ("pid", "uid", "start_ticks", "ticket_hash", "manifest_hash",
                   "release_sig_hash", "nonce", "seq")
PREPARED_FIELDS = ("seq", "release", "digest", "manifest_hash",
                   "release_sig_hash", "ticket_hash", "nonce", "previous_seq",
                   "previous_digest")
TICKET_FIELDS = old.FIELDS | frozenset((
    "manifest_sha256", "release_signature_sha256", "source_commit"))
HANDOFF_FIELDS = (
    "schema", "seq", "prepared_hash", "release", "digest",
    "manifest_hash", "release_sig_hash", "previous_seq", "previous_digest",
    "from_nonce", "from_ticket_hash", "from_pid", "from_start_ticks",
    "to_nonce", "to_ticket_hash", "to_pid", "to_start_ticks")

CLIENT_UID = 65534  # Disposable CI test principal; NOT product policy.


def dig(raw):
    return hashlib.sha256(raw).hexdigest()


def pid_identity(pid):
    """Kernel process identity for this CI principal, including PID reuse hint.

    Linux /proc start ticks disambiguates a reused pid in tests. This does NOT
    protect same-UID ptrace/injection into an approved ordinary user process.
    """
    if type(pid) is not int or pid <= 0:
        old.reject("untrusted sender PID")
    try:
        with open("/proc/%d/status" % pid, encoding="ascii") as stream:
            lines = stream.readlines()
        uids = next(line.split()[1:] for line in lines if line.startswith("Uid:"))
        if len(uids) != 4 or any(int(u) != CLIENT_UID for u in uids):
            old.reject("sender UID identity not verified by kernel")
        with open("/proc/%d/stat" % pid, encoding="ascii") as stream:
            line = stream.read()
        # /proc/<pid>/stat fields 3 onward follow the last ')' in comm.
        ticks = int(line.rsplit(")", 1)[1].split()[19])
    except (OSError, StopIteration, IndexError, ValueError):
        old.reject("sender process no longer authenticated")
    return {"pid":pid, "uid":CLIENT_UID, "start_ticks":ticks}


def provision_extra(root_path):
    """Create only CI root-owned additional private directories (no cleanup)."""
    old.guard()
    broker = old.Broker(root_path)
    try:
        for name in ("approval", "prepared", "handoff"):
            try:
                os.mkdir(name, 0o700, dir_fd=broker.dirs["private"])
            except FileExistsError:
                pass
            fd = old.open_dir(broker.dirs["private"], name)
            os.close(fd)
    finally:
        broker.close()


class BrokerV2(old.Broker):
    """Isolated CI replacement, not installed; original Broker remains frozen."""

    def __init__(self, root_path):
        super().__init__(root_path)
        try:
            self.dirs["approval"] = old.open_dir(self.dirs["private"], "approval")
            self.dirs["prepared"] = old.open_dir(self.dirs["private"], "prepared")
            self.dirs["handoff"] = old.open_dir(self.dirs["private"], "handoff")
        except BaseException:
            self.close()
            raise

    def signed_release(self, manifest, release_sig, *, previous, now):
        return signed.verify_metadata(
            manifest, release_sig, self.release_pins,
            expected_platform="linux", expected_arch="x86_64",
            minimum_sequence=0 if previous is None else previous["seq"] + 1,
            now=now)

    def authorize_v2(self, ticket, ticket_sig, manifest, release_sig,
                     meta, previous, *, now):
        obj = old.parse(ticket)
        if set(obj) != TICKET_FIELDS or len(ticket_sig) != 64:
            old.reject("v2 exact-manifest operation authorization required")
        if (type(obj["schema"]) is not int or obj["schema"] != 2
                or obj["op"] != "activate"
                or obj["app_id"] != signed.APP_ID
                or obj["channel"] != signed.CHANNEL
                or type(obj["sequence"]) is not int
                or obj["sequence"] != meta.sequence
                or obj["digest"] != meta.artifact_sha256
                or obj["source_commit"] != meta.source_commit
                or obj["manifest_sha256"] != dig(manifest)
                or obj["release_signature_sha256"] != dig(release_sig)
                or obj["previous_seq"] !=
                   (previous["seq"] if previous else None)
                or obj["previous_digest"] !=
                   (previous["digest"] if previous else None)
                or type(obj["nonce"]) is not str
                or not old.NONCE.fullmatch(obj["nonce"])
                or type(obj["not_before"]) is not int
                or type(obj["expires_at"]) is not int
                or obj["not_before"] > now
                or obj["expires_at"] < now
                or obj["expires_at"] - obj["not_before"] > 300):
            old.reject("operation does not bind exact signed manifest and source")
        try:
            Ed25519PublicKey.from_public_bytes(self.operation_pin).verify(
                ticket_sig, DOMAIN + ticket)
        except (InvalidSignature, ValueError):
            old.reject("independent v2 operation signer rejected")
        return obj

    @staticmethod
    def approval_name(nonce):
        if type(nonce) is not str or not old.NONCE.fullmatch(nonce):
            old.reject("invalid operation nonce")
        return "grant-" + nonce + ".json"

    @staticmethod
    def prepared_name(sequence):
        if type(sequence) is not int or sequence < 0:
            old.reject("invalid transaction sequence")
        return "prep-%020d.json" % sequence

    def approval_record(self, obj, manifest, release_sig, ticket, pid):
        ident = pid_identity(pid)
        return {**ident, "ticket_hash": dig(ticket),
                "manifest_hash": dig(manifest),
                "release_sig_hash":dig(release_sig),
                "nonce":obj["nonce"], "seq":obj["sequence"]}

    def approve_from_root_test_authority(
            self, manifest, release_sig, ticket, ticket_sig, sender_pid, *,
            now=old.CI_NOW):
        """ROOT-ONLY sideband; NOT an IPC endpoint or independent human consent.

        Called solely from the privileged CI test harness after a named client
        process is started. A normal client cannot self-issue this approval.
        """
        old.guard()
        with self.lock():
            records = self.commits()
            previous = self.reconcile(records)
            meta = self.signed_release(manifest, release_sig,
                                       previous=previous, now=now)
            ticket_obj = self.authorize_v2(
                ticket, ticket_sig, manifest, release_sig, meta, previous,
                now=now)
            record = self.approval_record(
                ticket_obj, manifest, release_sig, ticket, sender_pid)
            old.write_new(self.dirs["approval"],
                          self.approval_name(ticket_obj["nonce"]),
                          self.signed_record(record))
            return record

    def check_independent_approval(
            self, obj, manifest, release_sig, ticket, credentials):
        if (type(credentials) is not tuple or len(credentials) != 3):
            old.reject("kernel per-message credentials required")
        pid, uid, gid = credentials
        if uid != CLIENT_UID or gid != CLIENT_UID:
            old.reject("unapproved kernel message credentials")
        receipt = old.read_file(
            self.dirs["approval"], self.approval_name(obj["nonce"]),
            maximum=4096)
        if receipt is None:
            old.reject("missing separate root-side per-operation approval")
        record = self.verify_record(receipt, APPROVAL_FIELDS)
        expected = self.approval_record(
            obj, manifest, release_sig, ticket, pid)
        if record != expected:
            old.reject("independent approval not bound to this sender/session")
        return True

    def prepared_record(self, obj, manifest, release_sig, ticket, meta,
                        release, previous):
        return {
            "seq":meta.sequence, "release":release,
            "digest":meta.artifact_sha256,
            "manifest_hash":dig(manifest),
            "release_sig_hash":dig(release_sig),
            "ticket_hash":dig(ticket), "nonce":obj["nonce"],
            "previous_seq":previous["seq"] if previous else None,
            "previous_digest":previous["digest"] if previous else None}

    @staticmethod
    def handoff_name(sequence):
        if type(sequence) is not int or sequence < 0:
            old.reject("invalid takeover sequence")
        return "transfer-%020d.json" % sequence

    def protected_preparation(self, sequence):
        raw = old.read_file(
            self.dirs["prepared"], self.prepared_name(sequence), maximum=4096)
        if raw is None:
            old.reject("no authenticated original prepared transaction")
        record = self.verify_record(raw, PREPARED_FIELDS)
        if (type(record["seq"]) is not int or record["seq"] != sequence
                or type(record["nonce"]) is not str
                or not old.NONCE.fullmatch(record["nonce"])):
            old.reject("invalid original prepared transaction")
        return raw, record

    def protected_approval_for(self, nonce, receipt):
        raw = old.read_file(
            self.dirs["approval"], self.approval_name(nonce), maximum=4096)
        if raw is None:
            old.reject("missing protected original or replacement approval")
        grant = self.verify_record(raw, APPROVAL_FIELDS)
        if (type(grant["pid"]) is not int
                or type(grant["start_ticks"]) is not int
                or grant["start_ticks"] <= 0
                or grant["uid"] != CLIENT_UID
                or grant["nonce"] != nonce
                or grant["seq"] != receipt["seq"]
                or grant["ticket_hash"] != receipt["ticket_hash"]
                or grant["manifest_hash"] != receipt["manifest_hash"]
                or grant["release_sig_hash"] != receipt["release_sig_hash"]):
            old.reject("original/replacement authority does not match prepared bytes")
        return grant

    @staticmethod
    def original_identity_gone(grant):
        """Explicit root-side process-death check, fail closed if ambiguous.

        A zombie still in /proc is conservatively considered alive. Start ticks
        are a CI PID-reuse hint, NOT a production pidfd/session guarantee.
        """
        pid = grant["pid"]
        if type(pid) is not int or pid <= 0:
            old.reject("untrusted original process identity")
        try:
            with open("/proc/%d/stat" % pid, encoding="ascii") as handle:
                data = handle.read()
        except FileNotFoundError:
            return True
        except OSError:
            old.reject("original process identity cannot be verified")
        try:
            current_start = int(data.rsplit(")", 1)[1].split()[19])
        except (ValueError, IndexError):
            old.reject("unverifiable original process identity")
        if current_start == grant["start_ticks"]:
            old.reject("original approved process is still alive")
        return True  # Previously approved PID has been recycled.

    @staticmethod
    def compare_immutable_prepared(original, replacement):
        keys = ("seq", "release", "digest", "manifest_hash", "release_sig_hash",
                "previous_seq", "previous_digest")
        if any(original[k] != replacement[k] for k in keys):
            old.reject("takeover would change original signed manifest/state")
        if original["nonce"] == replacement["nonce"]:
            old.reject("replacement must have independently signed NEW nonce")

    def build_handoff(self, prepared_raw, original, replacement, new_pid):
        """Recompute a full transfer authorization from ROOT-owned evidence."""
        self.compare_immutable_prepared(original, replacement)
        source = self.protected_approval_for(original["nonce"], original)
        self.original_identity_gone(source)
        destination = self.protected_approval_for(replacement["nonce"], replacement)
        observed = pid_identity(new_pid)
        if destination["pid"] != observed["pid"] or (
                destination["start_ticks"] != observed["start_ticks"]):
            old.reject("replacement sender not independently root approved")
        if (source["pid"], source["start_ticks"]) == (
                destination["pid"], destination["start_ticks"]):
            old.reject("replacement is not a new approved session")
        return {
            "schema":1, "seq":original["seq"],
            "prepared_hash":dig(prepared_raw),
            "release":original["release"], "digest":original["digest"],
            "manifest_hash":original["manifest_hash"],
            "release_sig_hash":original["release_sig_hash"],
            "previous_seq":original["previous_seq"],
            "previous_digest":original["previous_digest"],
            "from_nonce":original["nonce"],
            "from_ticket_hash":original["ticket_hash"],
            "from_pid":source["pid"], "from_start_ticks":source["start_ticks"],
            "to_nonce":replacement["nonce"],
            "to_ticket_hash":replacement["ticket_hash"],
            "to_pid":destination["pid"],
            "to_start_ticks":destination["start_ticks"]}

    def authorize_takeover_from_root_test_authority(
            self, manifest, release_sig, ticket, ticket_sig,
            replacement_pid, *, now=old.CI_NOW):
        """ROOT-ONLY independent handoff decision, never a client IPC command.

        Requires BOTH independently root-approved original and new operations.
        The original PID must be dead. Record is immutable, authenticated and
        fsynced before new process can adopt a staged root-owned release.
        """
        old.guard()
        with self.lock():
            committed = self.commits()
            previous = self.reconcile(committed)
            meta = self.signed_release(
                manifest, release_sig, previous=previous, now=now)
            obj = self.authorize_v2(
                ticket, ticket_sig, manifest, release_sig, meta, previous,
                now=now)
            if any(item["nonce"] == obj["nonce"] for item in committed):
                old.reject("committed nonce cannot be transferred")
            self.check_independent_approval(
                obj, manifest, release_sig, ticket,
                (replacement_pid, CLIENT_UID, CLIENT_UID))
            original_raw, original = self.protected_preparation(meta.sequence)
            release = "rel-%020d-%s.bin" % (
                meta.sequence, meta.artifact_sha256[:16])
            replacement = self.prepared_record(
                obj, manifest, release_sig, ticket, meta, release, previous)
            transfer = self.build_handoff(
                original_raw, original, replacement, replacement_pid)
            # If the root-owned orphan exists, validate it BEFORE authorizing
            # adoption. A foreign or changed byte stays untouched on denial.
            blob = old.read_file(self.dirs["release"], release)
            if blob is not None and (
                    len(blob) != meta.artifact_size
                    or dig(blob) != meta.artifact_sha256):
                old.reject("foreign/altered orphan cannot be transferred")
            name = self.handoff_name(meta.sequence)
            existing = old.read_file(self.dirs["handoff"], name, maximum=4096)
            if existing is not None:
                if self.verify_record(existing, HANDOFF_FIELDS) != transfer:
                    old.reject("different/foreign transfer record already exists")
                return transfer  # Idempotent EXACT root approval.
            old.write_new(self.dirs["handoff"], name,
                          self.signed_record(transfer))
            return transfer

    def assert_authenticated_takeover(
            self, prepared_raw, original, replacement, credentials):
        if (type(credentials) is not tuple or len(credentials) != 3
                or credentials[1:] != (CLIENT_UID, CLIENT_UID)):
            old.reject("kernel sender credentials missing for takeover")
        transfer_raw = old.read_file(
            self.dirs["handoff"], self.handoff_name(original["seq"]),
            maximum=4096)
        if transfer_raw is None:
            old.reject("replacement lacks independent protected transfer")
        transfer = self.verify_record(transfer_raw, HANDOFF_FIELDS)
        expected = self.build_handoff(
            prepared_raw, original, replacement, credentials[0])
        if transfer != expected:
            old.reject("authenticated transfer does not match new session")
        return True

    def stage_or_retry(self, record, data, *, credentials=None, cut=None):
        """Adopt only protected signed-prepared orphan; foreign bytes untouched.

        Receipt is HMAC-authenticated and committed BEFORE blob creation, so a
        crash after blob fsync can be safely resumed only with the same exact
        signed ticket and manifest under the broker lock.
        """
        name = self.prepared_name(record["seq"])
        previous = old.read_file(self.dirs["prepared"], name, maximum=4096)
        existing = old.read_file(self.dirs["release"], record["release"])
        if previous is None:
            if existing is not None:
                old.reject("foreign release exists without protected prepare receipt")
            old.write_new(self.dirs["prepared"], name, self.signed_record(record))
            if cut == "after_prepare":
                raise old.Cut("authenticated prepare without staged bytes")
        else:
            authenticated = self.verify_record(previous, PREPARED_FIELDS)
            if authenticated != record:
                # Strict unchanged original prepare; only a separately
                # root-authorized, immutable handoff can replace ticket/nonce.
                self.assert_authenticated_takeover(
                    previous, authenticated, record, credentials)
        if existing is None:
            old.write_new(self.dirs["release"], record["release"], data)
        elif (len(existing) != len(data) or dig(existing) != record["digest"]
              or existing != data):
            old.reject("prepared orphan bytes changed: preserve and HOLD")
        # read_file + owned() checks root UID, no group/other writable bits,
        # st_nlink == 1, O_NOFOLLOW and exact SHA256 from root-owned namespace.
        final = old.read_file(self.dirs["release"], record["release"])
        if final != data:
            old.reject("prepared release identity changed during staging")
        return record["release"]

    def activate(self, fd, manifest, release_sig, ticket, ticket_sig, *,
                 credentials, now, cut=None):
        """Every client operation requires exact signed manifest AND root approval."""
        with self.lock():
            entries = self.commits()
            previous = self.reconcile(entries)
            meta = self.signed_release(manifest, release_sig,
                                       previous=previous, now=now)
            obj = self.authorize_v2(
                ticket, ticket_sig, manifest, release_sig, meta, previous,
                now=now)
            if any(item["nonce"] == obj["nonce"] for item in entries):
                old.reject("replayed independently approved operation")
            self.check_independent_approval(
                obj, manifest, release_sig, ticket, credentials)
            data = self.verify_fd(fd, meta)
            release = "rel-%020d-%s.bin" % (
                meta.sequence, meta.artifact_sha256[:16])
            receipt = self.prepared_record(
                obj, manifest, release_sig, ticket, meta, release, previous)
            self.stage_or_retry(
                receipt, data, credentials=credentials, cut=cut)
            if cut == "after_release":
                raise old.Cut("prepared release without journal")
            commit = {
                "seq":meta.sequence, "release":release,
                "digest":meta.artifact_sha256,
                "previous_seq":receipt["previous_seq"],
                "previous_digest":receipt["previous_digest"],
                "nonce":obj["nonce"],
                "manifest_hash":receipt["manifest_hash"],
                "ticket_hash":receipt["ticket_hash"]}
            old.write_new(self.dirs["journal"],
                          "txn-%020d.json" % meta.sequence,
                          self.signed_record(commit))
            if cut == "after_journal":
                raise old.Cut("authenticated journal committed before activation")
            self.publish(commit)
            return {key:commit[key] for key in ("seq", "release", "digest")}


def receive_v2(sock):
    """Exactly one SCM_RIGHTS + per-MESSAGE SCM_CREDENTIALS, not SO_PEERCRED.

    SO_PASSCRED must be set on the accepted connected socket before recvmsg.
    Inherited sockets reveal sender of this message (fork child), not only
    SO_PEERCRED's socket-creation identity. Close malformed received FD.
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    size = array.array("i").itemsize
    frame, anc, flags, _ = sock.recvmsg(16384,
        socket.CMSG_SPACE(16 * size) + socket.CMSG_SPACE(struct.calcsize("3i")),
        socket.MSG_CMSG_CLOEXEC)
    fds, creds = [], []
    try:
        for level, typ, raw in anc:
            if (level, typ) == (socket.SOL_SOCKET, socket.SCM_RIGHTS):
                values = array.array("i")
                values.frombytes(raw[:len(raw) - len(raw) % size])
                fds.extend(values)
            elif (level, typ) == (socket.SOL_SOCKET, socket.SCM_CREDENTIALS):
                if len(raw) != struct.calcsize("3i"):
                    old.reject("malformed per-message kernel credentials")
                creds.append(struct.unpack("3i", raw))
        if (flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
                or len(fds) != 1 or len(creds) != 1):
            old.reject("exactly one FD and kernel message credential required")
        data = old.parse(frame)
        if set(data) != {"metadata", "release_sig", "ticket", "ticket_sig"}:
            old.reject("invalid operation frame")
        values = []
        for key in ("metadata", "release_sig", "ticket", "ticket_sig"):
            try:
                values.append(base64.b64decode(data[key], validate=True))
            except (TypeError, ValueError):
                old.reject("invalid binary field")
        fd = fds.pop()
        return fd, tuple(values), creds[0]
    finally:
        for fd in fds:
            os.close(fd)


def server(root_path):
    """No root approval service is exposed: fail closed for stolen bearer."""
    old.guard()
    b = BrokerV2(root_path)
    b.recover()
    path = str(Path(root_path) / "broker.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        # Kernel SCM_CREDENTIALS must be attached at enqueue time. Setting
        # SO_PASSCRED after accept/recv may yield an SCM_CREDENTIALS pid=0
        # for a frame already queued before the receiver toggles it.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        s.bind(path)
        os.chmod(path, 0o666)
        s.listen(6)
        print("READY", flush=True)
        while True:
            conn, _ = s.accept()
            with conn:
                conn.settimeout(3)
                fd = None
                try:
                    fd, parts, peer = receive_v2(conn)
                    result = b.activate(fd, *parts,
                                        credentials=peer, now=old.CI_NOW)
                    reply = {"ok":True, "result":result,
                             "message_sender_uid":peer[1]}
                except Exception as exc:
                    reply = {"ok":False,"error":str(exc)[:220]}
                finally:
                    if fd is not None:
                        os.close(fd)
                # Unauthenticated peers may close, reset or time out while
                # the broker is preparing a reply. Never let a failed
                # response kill the privileged accept loop.
                try:
                    conn.sendall(old.canonical(reply))
                except (BrokenPipeError, ConnectionResetError,
                        ConnectionAbortedError, TimeoutError, OSError):
                    pass
    finally:
        s.close()
        b.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "server":
        server(sys.argv[2])
    else:
        raise SystemExit("GitHub-hosted disposable CI server only")
