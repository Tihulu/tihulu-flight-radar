#!/usr/bin/env python3
"""Agent08 ROOT-vs-nobody security acceptance: real Linux DAC + signed tickets.

Run ONLY via sudo on disposable GitHub-hosted Ubuntu. Separate exec'd
unprivileged (UID 65534) clients have no signing private keys. The root broker
is a temporary user-space subprocess, NOT an installed privileged service.
Prior Agent 06 33 positive-vulnerability tests stay unchanged in this PR.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import flight_p1_broker_os_boundary_ci as b
from tools import flight_signed_installer_ci_prototype as signed

BLOB = b"ROOT-SEPARATED-BROKER-EPHEMERAL-CI-ARTIFACT"
NOW = b.CI_NOW
UNPRIV = 65534


def pub(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


def drop():
    os.setgroups([])
    os.setresgid(UNPRIV, UNPRIV, UNPRIV)
    os.setresuid(UNPRIV, UNPRIV, UNPRIV)


@unittest.skipUnless(sys.platform == "linux", "Linux privilege boundary only")
class RealUIDBrokerTests(unittest.TestCase):
    def setUp(self):
        b.guard()
        if os.getuid() != 0:
            self.skipTest("need disposable root CI")
        self.tmp = tempfile.TemporaryDirectory(
            prefix="flight-agent08-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.release_key = Ed25519PrivateKey.generate()
        self.operation_key = Ed25519PrivateKey.generate()
        b.provision(self.root, pub(self.release_key), pub(self.operation_key))
        self.public = self.root / "public"
        self.public.mkdir(mode=0o755)
        self.sock = self.root / "broker.sock"
        self.worker = None
        self.addCleanup(self.stop_server)
        self.counter = 0
        self.env = {
            "CI":"true", "GITHUB_ACTIONS":"true",
            "RUNNER_TEMP":os.environ["RUNNER_TEMP"],
            "PYTHONPATH":os.getcwd(), "PATH":os.environ.get("PATH","/usr/bin"),
            "PYTHONDONTWRITEBYTECODE":"1", "HOME":"/tmp",
            "LANG":"C.UTF-8"}
        self.start_server()

    def start_server(self):
        self.worker = subprocess.Popen(
            [sys.executable, "-m", "tools.flight_p1_broker_os_boundary_ci",
             "server", str(self.root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=self.env, cwd=os.getcwd(), start_new_session=True)
        readable, _, _ = select.select([self.worker.stdout], [], [], 8)
        if not readable:
            self.stop_server()
            self.fail("privileged test subprocess never started")
        line = self.worker.stdout.readline().strip()
        if line != "READY":
            err = self.worker.stderr.read() if self.worker.poll() is not None else ""
            self.stop_server()
            self.fail("broker failed startup: " + line + " " + err)
        self.assertTrue(self.sock.exists())

    def stop_server(self):
        if self.worker is not None:
            if self.worker.poll() is None:
                self.worker.terminate()
                try:
                    self.worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.worker.kill()
                    self.worker.wait(timeout=5)
            self.worker.stdout.close()
            self.worker.stderr.close()
            self.worker = None
        if getattr(self, "sock", None) is not None and self.sock.exists():
            self.sock.unlink()

    def payload(self, *, seq=50, data=BLOB, previous=None,
                bad_release_key=None, bad_operation_key=None,
                op="activate", nonce=None):
        meta = dict(
            schema=signed.SCHEMA, app_id=signed.APP_ID,
            channel=signed.CHANNEL, platform="linux", architecture="x86_64",
            artifact_name="artifact.bin", artifact_size=len(data),
            artifact_sha256=hashlib.sha256(data).hexdigest(),
            sequence=seq, issued_at=NOW - 100, expires_at=NOW + 100,
            source_commit="b" * 40, key_id="test-root")
        raw = signed.canonical_bytes(meta)
        release_sig = (bad_release_key or self.release_key).sign(
            signed.DOMAIN + raw)
        ticket = dict(schema=1, op=op, app_id=signed.APP_ID,
            channel=signed.CHANNEL, sequence=seq,
            digest=meta["artifact_sha256"],
            previous_seq=previous["seq"] if previous else None,
            previous_digest=previous["digest"] if previous else None,
            nonce=nonce or secrets.token_hex(16),
            not_before=NOW - 10, expires_at=NOW + 10)
        auth = b.canonical(ticket)
        auth_sig = (bad_operation_key or self.operation_key).sign(b.DOMAIN+auth)
        frame = b.canonical({
            "metadata":base64.b64encode(raw).decode("ascii"),
            "release_sig":base64.b64encode(release_sig).decode("ascii"),
            "ticket":base64.b64encode(auth).decode("ascii"),
            "ticket_sig":base64.b64encode(auth_sig).decode("ascii")})
        return frame, data, (raw, release_sig, auth, auth_sig)

    def make_files(self, frame, data):
        self.counter += 1
        a = self.public / ("frame-%02d.json" % self.counter)
        c = self.public / ("blob-%02d.bin" % self.counter)
        a.write_bytes(frame)
        c.write_bytes(data)
        a.chmod(0o644)
        c.chmod(0o644)
        return a, c

    def request(self, frame, data):
        f, artifact = self.make_files(frame, data)
        cp = subprocess.run(
            [sys.executable, "-m", "tools.flight_p1_broker_os_boundary_ci",
             "client", str(self.sock), str(f), str(artifact)],
            capture_output=True, text=True, timeout=14, cwd=os.getcwd(),
            env=self.env, preexec_fn=drop)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertTrue(cp.stdout.strip(), cp.stderr)
        return json.loads(cp.stdout.strip())

    def active(self):
        obj = b.Broker(self.root)
        try:
            return obj.active()
        finally:
            obj.close()

    def ledger(self):
        obj = b.Broker(self.root)
        try:
            return obj.commits()
        finally:
            obj.close()

    def unpriv_action(self, code, *params):
        return subprocess.run(
            [sys.executable, "-c", code, *map(str,params)],
            capture_output=True, text=True, timeout=8,
            cwd=os.getcwd(), env=self.env, preexec_fn=drop)

    def test_01_actual_distinct_kernel_uids_and_dac_not_python_guard(self):
        self.assertEqual(os.geteuid(), 0)
        cp = self.unpriv_action("import os;print(os.geteuid())")
        self.assertEqual(cp.returncode, 0)
        self.assertEqual(cp.stdout.strip(), str(UNPRIV))
        self.assertNotEqual(os.geteuid(), UNPRIV)
        self.assertEqual((self.root / "private").stat().st_uid, 0)
        self.assertEqual((self.root / "private").stat().st_mode & 0o777, 0o700)

    def test_02_foreign_uid_cannot_overwrite_journal_release_activation(self):
        frame, data, _ = self.payload()
        self.assertTrue(self.request(frame, data)["ok"])
        prior = self.active()
        journal = self.root / "private" / "journal"
        active = self.root / "private" / "active" / "active.json"
        release = self.root / "private" / "release" / prior["release"]
        for target in (journal/"txn-00000000000000000050.json", active, release):
            cp = self.unpriv_action(
                "from pathlib import Path;import sys;"
                "Path(sys.argv[1]).write_bytes(b'FOREIGN-UNSIGNED-ATTACK')",
                target)
            self.assertNotEqual(cp.returncode, 0, str(target))
            self.assertIn("PermissionError", cp.stderr)
        self.assertEqual(self.active(), prior)
        self.assertEqual(len(self.ledger()), 1)

    def test_03_foreign_uid_cannot_swap_public_parent_even_with_pinned_fd(self):
        cp = self.unpriv_action(
            "import os,sys;os.rename(sys.argv[1],sys.argv[2])",
            self.root, "/tmp/attacker-stolen-flight-agent08")
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("PermissionError", cp.stderr)
        self.assertTrue(self.root.is_dir())
        self.assertEqual(self.worker.poll(), None)

    def test_04_same_uid_client_without_independently_signed_ticket_denied(self):
        frame, data, parts = self.payload(bad_operation_key=Ed25519PrivateKey.generate())
        response = self.request(frame, data)
        self.assertFalse(response["ok"])
        self.assertIn("operation signer", response["error"])
        self.assertEqual(self.ledger(), [])
        self.assertIsNone(self.active())

    def test_05_valid_unprivileged_scm_rights_and_per_operation_ticket(self):
        frame, data, _ = self.payload()
        response = self.request(frame, data)
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["peer_uid"], UNPRIV)
        self.assertEqual(response["result"]["seq"], 50)
        self.assertEqual(self.active()["seq"], 50)
        self.assertEqual(self.ledger()[0]["seq"], 50)

    def test_06_signed_ticket_replay_and_release_downgrade_rejected(self):
        frame, data, _ = self.payload()
        self.assertTrue(self.request(frame, data)["ok"])
        replay = self.request(frame, data)
        self.assertFalse(replay["ok"])
        self.assertIn("sequence", replay["error"].lower())
        downgrade, blob, _ = self.payload(seq=49)
        self.assertFalse(self.request(downgrade, blob)["ok"])
        self.assertEqual(self.active()["seq"], 50)

    def test_07_valid_second_version_preserves_original_and_lineage(self):
        frame, data, _ = self.payload()
        self.assertTrue(self.request(frame, data)["ok"])
        first = self.active()
        second_blob = b"INERT-VERSION-51-ROOT-OWNED"
        second, blob, _ = self.payload(seq=51, previous=first, data=second_blob)
        self.assertTrue(self.request(second, blob)["ok"])
        self.assertEqual(self.active()["seq"], 51)
        self.assertEqual([e["seq"] for e in self.ledger()], [50,51])
        self.assertEqual((self.root/"private"/"release"/first["release"]).read_bytes(),
                         BLOB)

    def test_08_bad_previous_activation_or_operation_scope_rejected(self):
        frame, data, _ = self.payload()
        self.assertTrue(self.request(frame, data)["ok"])
        current = self.active()
        wrongprev, blob, _ = self.payload(seq=51, previous=None)
        self.assertFalse(self.request(wrongprev,blob)["ok"])
        wrongop, blob, _ = self.payload(seq=51, previous=current, op="rollback")
        self.assertFalse(self.request(wrongop,blob)["ok"])
        self.assertEqual(self.active()["seq"], 50)

    def test_09_forged_release_root_self_supply_cannot_override_pinned_key(self):
        frame, data, _ = self.payload(bad_release_key=Ed25519PrivateKey.generate())
        response = self.request(frame, data)
        self.assertFalse(response["ok"])
        self.assertEqual(self.ledger(), [])

    def test_10_transferred_sealed_fd_wrong_bytes_denied_by_root_process(self):
        frame, data, _ = self.payload()
        result = self.request(frame, b"Z" * len(data))
        self.assertFalse(result["ok"])
        self.assertIn("FD", result["error"])
        self.assertIsNone(self.active())

    def test_11_unsigned_journal_forgery_cannot_drive_privileged_recovery(self):
        bad = self.root/"private"/"journal"/"txn-00000000000000000999.json"
        cp = self.unpriv_action(
            "from pathlib import Path;import sys;"
            "Path(sys.argv[1]).write_text('unsigned',encoding='ascii')", bad)
        self.assertNotEqual(cp.returncode, 0)
        obj = b.Broker(self.root)
        try:
            self.assertIsNone(obj.recover())
        finally:
            obj.close()
        self.assertFalse(bad.exists())

    def test_12_journal_compare_replace_race_has_no_writable_target(self):
        first, data, _ = self.payload()
        self.assertTrue(self.request(first, data)["ok"])
        before = self.active()
        target = self.root/"private"/"journal"/"txn-00000000000000000051.json"
        outsider = self.root/"public"/"foreign-settings.bin"
        outsider.write_bytes(b"FOREIGN-SURVIVES")
        attacker = self.unpriv_action(
            "from pathlib import Path;import sys;"
            "Path(sys.argv[1]).write_bytes(b'FOREIGN-JOURNAL-CLAIM')", target)
        self.assertNotEqual(attacker.returncode, 0)
        second, data, _ = self.payload(seq=51, previous=before,
                                       data=b"SIGNED-NEXT-VERSION-51")
        self.assertTrue(self.request(second,data)["ok"])
        self.assertEqual(outsider.read_bytes(), b"FOREIGN-SURVIVES")
        self.assertEqual([e["seq"] for e in self.ledger()], [50, 51])
        self.assertEqual(self.active()["seq"], 51)
        # No compare+replace of journal record: each txn file is created O_EXCL.
        self.assertTrue(target.exists())

    def test_13_crash_after_authenticated_journal_restart_replays_verified(self):
        self.stop_server()
        data = BLOB
        frame, _, (raw, sig, ticket, authsig) = self.payload()
        fd = os.memfd_create("agent08-root-crash", os.MFD_ALLOW_SEALING)
        try:
            os.write(fd, data)
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, b.REQUIRED_SEALS)
            model = b.Broker(self.root)
            try:
                with self.assertRaises(b.Cut):
                    model.activate(fd,raw,sig,ticket,authsig,
                                   now=NOW,cut="after_journal")
                self.assertIsNone(model.active())
                self.assertEqual(len(model.commits()), 1)
            finally:
                model.close()
        finally:
            os.close(fd)
        self.start_server()   # separate new root process executes recover()
        self.assertEqual(self.active()["seq"],50)
        self.assertEqual(self.ledger()[0]["seq"],50)

    def test_14_crash_before_journal_never_activates_uncommitted_release(self):
        self.stop_server()
        data=BLOB
        frame, _, (raw,sig,ticket,authsig)=self.payload()
        fd=os.memfd_create("agent08-root-crash2",os.MFD_ALLOW_SEALING)
        try:
            os.write(fd,data)
            fcntl.fcntl(fd,fcntl.F_ADD_SEALS,b.REQUIRED_SEALS)
            model=b.Broker(self.root)
            try:
                with self.assertRaises(b.Cut):
                    model.activate(fd,raw,sig,ticket,authsig,
                                   now=NOW,cut="after_release")
                self.assertIsNone(model.active())
                self.assertEqual(model.commits(),[])
            finally:
                model.close()
        finally:
            os.close(fd)
        self.start_server()
        self.assertIsNone(self.active())
        self.assertEqual(self.ledger(), [])
        self.assertEqual(len(list((self.root/"private"/"release").glob("rel-*"))),1)

    def test_15_corrupt_root_journal_mac_is_fail_closed_not_recovered(self):
        frame,data,_=self.payload()
        self.assertTrue(self.request(frame,data)["ok"])
        self.stop_server()
        record=self.root/"private"/"journal"/"txn-00000000000000000050.json"
        before=record.read_bytes()
        modified=before.replace(b'"seq":50',b'"seq":51')
        record.write_bytes(modified)
        obj=b.Broker(self.root)
        try:
            with self.assertRaises(b.Denied):
                obj.recover()
        finally:
            obj.close()
        self.assertEqual(record.read_bytes(),modified)

    def test_16_socket_peer_uid_is_channel_telemetry_not_consent(self):
        forged,blob,_=self.payload(bad_operation_key=Ed25519PrivateKey.generate())
        outcome=self.request(forged,blob)
        self.assertFalse(outcome["ok"])
        self.assertIsNone(self.active())
        valid,blob,_=self.payload()
        response=self.request(valid,blob)
        self.assertTrue(response["ok"])
        self.assertEqual(response["peer_uid"],UNPRIV)
        # Both requests have IDENTICAL kernel UID; only external signed
        # operation authorization changes the activation decision.

    def test_17_no_authenticated_rollback_endpoint_or_shared_service_ops(self):
        self.assertFalse(b.Broker.__dict__.get("rollback"))
        self.assertFalse(hasattr(b.Broker,"stop_readsb"))
        self.assertFalse(hasattr(b.Broker,"acquire_sdr"))
        foreign=self.root/"public"/"recording-iq.raw"
        foreign.write_bytes(b"INDEPENDENT RECORDING")
        frame,blob,_=self.payload()
        self.assertTrue(self.request(frame,blob)["ok"])
        self.assertEqual(foreign.read_bytes(), b"INDEPENDENT RECORDING")

    def test_18_immutable_journal_entry_collision_is_fail_closed_and_preserved(self):
        # Privileged fixture simulates non-adversarial foreign collision. The
        # ordinary attacker cannot inject one (tested in #12).
        self.stop_server()
        collision=self.root/"private"/"journal"/"txn-00000000000000000050.json"
        foreign=b"FOREIGN-ROOT-OWNED-COLLISION"
        collision.write_bytes(foreign)
        model=b.Broker(self.root)
        try:
            with self.assertRaises(b.Denied):
                model.recover()
        finally:
            model.close()
        self.assertEqual(collision.read_bytes(),foreign)


if __name__ == "__main__":
    unittest.main(verbosity=2)
