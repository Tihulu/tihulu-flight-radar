#!/usr/bin/env python3
"""Agent08 PR52 fail-closed ACCEPTANCE for new broker-v2 only.

Old PR52 15 positive limits remain unchanged and run against FROZEN v1.
New tests exercise actual GitHub-hosted Linux ROOT vs separately exec'd
UID65534 clients; root-only test approval is NOT human consent or deployment.
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
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import flight_p1_broker_pr52_remediation_ci as v2
from tools import flight_p1_broker_os_boundary_ci as v1
from tools import flight_p1_broker_os_boundary_tests as oldtests
from tools import flight_signed_installer_ci_prototype as signed

BLOB = oldtests.BLOB
NOW = v1.CI_NOW
PAUSE = """import os,signal
print("READY",flush=True)
os.kill(os.getpid(),signal.SIGSTOP)
"""


@unittest.skipUnless(sys.platform == "linux", "Linux real UID boundary only")
class PR52RemediationAcceptance(unittest.TestCase):
    setUp = oldtests.RealUIDBrokerTests.setUp
    stop_server = oldtests.RealUIDBrokerTests.stop_server
    make_files = oldtests.RealUIDBrokerTests.make_files
    request = oldtests.RealUIDBrokerTests.request
    active = oldtests.RealUIDBrokerTests.active
    ledger = oldtests.RealUIDBrokerTests.ledger
    unpriv_action = oldtests.RealUIDBrokerTests.unpriv_action

    def start_server(self):
        if not (self.root / "private" / "approval").exists():
            v2.provision_extra(self.root)
        self.worker = subprocess.Popen(
            [sys.executable, "-m", "tools.flight_p1_broker_pr52_remediation_ci",
             "server", str(self.root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=self.env, cwd=os.getcwd(), start_new_session=True)
        ready, _, _ = select.select([self.worker.stdout], [], [], 8)
        if not ready:
            self.stop_server()
            self.fail("v2 broker did not start")
        line = self.worker.stdout.readline().strip()
        if line != "READY":
            error = self.worker.stderr.read() if self.worker.poll() is not None else ""
            self.stop_server()
            self.fail("v2 broker invalid start: " + line + " " + error)
        self.assertTrue(self.sock.exists())

    def root_model(self):
        model = v2.BrokerV2(self.root)
        self.addCleanup(model.close)
        return model

    def frame_v2(self, *, seq=50, data=BLOB, previous=None,
                 source_commit="b"*40, op="activate", nonce=None,
                 wrong_release=False, wrong_operation=False):
        fields = dict(
            schema=signed.SCHEMA, app_id=signed.APP_ID,
            channel=signed.CHANNEL, platform="linux", architecture="x86_64",
            artifact_name="artifact.bin", artifact_size=len(data),
            artifact_sha256=hashlib.sha256(data).hexdigest(),
            sequence=seq, issued_at=NOW - 100, expires_at=NOW + 100,
            source_commit=source_commit, key_id="test-root")
        manifest = signed.canonical_bytes(fields)
        rkey = Ed25519PrivateKey.generate() if wrong_release else self.release_key
        release_sig = rkey.sign(signed.DOMAIN + manifest)
        ticket = dict(
            schema=2, op=op, app_id=signed.APP_ID,
            channel=signed.CHANNEL, sequence=seq,
            digest=fields["artifact_sha256"],
            source_commit=source_commit,
            manifest_sha256=v2.dig(manifest),
            release_signature_sha256=v2.dig(release_sig),
            previous_seq=previous["seq"] if previous else None,
            previous_digest=previous["digest"] if previous else None,
            nonce=nonce or secrets.token_hex(16),
            not_before=NOW-10, expires_at=NOW+10)
        signed_ticket = v1.canonical(ticket)
        okey = Ed25519PrivateKey.generate() if wrong_operation else self.operation_key
        ticket_sig = okey.sign(v2.DOMAIN + signed_ticket)
        frame = self.reframe((manifest, release_sig, signed_ticket, ticket_sig))
        return frame, data, (manifest, release_sig, signed_ticket, ticket_sig)

    @staticmethod
    def reframe(parts):
        return v1.canonical({
            name:base64.b64encode(value).decode("ascii")
            for name,value in zip(("metadata","release_sig","ticket","ticket_sig"),
                                  parts)})

    def parked_client(self, frame, data, code=None):
        f, blob = self.make_files(frame, data)
        proc = subprocess.Popen(
            [sys.executable, "-c", PAUSE +
             (oldtests.UNPRIV_CLIENT if code is None else code),
             str(self.sock), str(f), str(blob)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=os.getcwd(), env=self.env, preexec_fn=oldtests.drop)
        def cleanup():
            if proc.poll() is None:
                try:
                    os.kill(proc.pid, signal.SIGCONT)
                    proc.terminate()
                    proc.wait(timeout=3)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    proc.kill()
                    proc.wait(timeout=3)
            proc.stdout.close()
            proc.stderr.close()
        self.addCleanup(cleanup)
        line = proc.stdout.readline().strip()
        self.assertEqual(line, "READY", "unprivileged process did not park")
        return proc

    def grant(self, proc, parts):
        root = v2.BrokerV2(self.root)
        try:
            return root.approve_from_root_test_authority(
                *parts, proc.pid, now=NOW)
        finally:
            root.close()

    def resume(self, proc):
        os.kill(proc.pid, signal.SIGCONT)
        out, err = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 0, err)
        result = json.loads(out.strip())
        return result

    def sealed_fd(self, data=BLOB):
        fd = os.memfd_create("agent08-v2-cut", os.MFD_ALLOW_SEALING |
                            os.MFD_CLOEXEC)
        os.write(fd,data)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, v1.REQUIRED_SEALS)
        self.addCleanup(os.close, fd)
        return fd

    def cut_as_approved(self, proc, parts, *, data=BLOB, cut="after_release"):
        m = v2.BrokerV2(self.root)
        try:
            with self.assertRaises(v1.Cut):
                m.activate(self.sealed_fd(data), *parts,
                           credentials=(proc.pid, oldtests.UNPRIV, oldtests.UNPRIV),
                           now=NOW, cut=cut)
        finally:
            m.close()

    def test_01_real_uid_stolen_unused_valid_ticket_denied_without_sideband_approval(self):
        frame, data, _ = self.frame_v2()
        reply = self.request(frame,data)
        self.assertFalse(reply["ok"])
        self.assertIn("root-side", reply["error"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_02_root_approved_single_process_commits_valid_transaction(self):
        frame, data, parts = self.frame_v2()
        proc = self.parked_client(frame,data)
        grant = self.grant(proc,parts)
        self.assertEqual(grant["pid"],proc.pid)
        accepted = self.resume(proc)
        self.assertTrue(accepted["ok"],accepted)
        self.assertEqual(accepted["message_sender_uid"],oldtests.UNPRIV)
        self.assertEqual(self.active()["seq"],50)
        self.assertEqual(self.ledger()[0]["nonce"],json.loads(parts[2])["nonce"])

    def test_03_stolen_ticket_different_same_uid_client_denied_even_with_existing_grant(self):
        frame, data, parts = self.frame_v2()
        legit = self.parked_client(frame,data)
        self.grant(legit,parts)
        attacker = self.request(frame,data)
        self.assertFalse(attacker["ok"])
        self.assertIn("not bound to this sender",attacker["error"])
        self.assertIsNone(self.active())
        self.assertTrue(self.resume(legit)["ok"])
        self.assertEqual(len(self.ledger()),1)

    def test_04_actual_kernel_denies_attacker_writing_root_only_approval_file(self):
        frame,data,parts = self.frame_v2()
        nonce=json.loads(parts[2])["nonce"]
        target=self.root/"private"/"approval"/v2.BrokerV2.approval_name(nonce)
        cp=self.unpriv_action("from pathlib import Path;import sys;"
                              "Path(sys.argv[1]).write_bytes(b'ATTACK')",target)
        self.assertNotEqual(cp.returncode,0)
        self.assertIn("PermissionError",cp.stderr)
        self.assertFalse(self.request(frame,data)["ok"])
        self.assertFalse(target.exists())

    def test_05_full_manifest_source_commit_switch_rejected_under_same_ticket(self):
        frame, data, parts = self.frame_v2()
        alternate = dict(json.loads(parts[0]),source_commit="c"*40)
        raw = signed.canonical_bytes(alternate)
        release_sig = self.release_key.sign(signed.DOMAIN + raw)
        self.assertEqual(alternate["artifact_sha256"],json.loads(parts[0])["artifact_sha256"])
        self.assertNotEqual(v2.dig(raw),v2.dig(parts[0]))
        changed = self.reframe((raw,release_sig,parts[2],parts[3]))
        proc = self.parked_client(changed,data)
        self.grant(proc,parts)  # Trusted approver approved ORIGINAL manifest.
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertIn("exact signed manifest",reply["error"])
        self.assertEqual(self.ledger(),[])

    def test_06_v2_signature_or_operation_scope_rejection_still_fail_closed(self):
        for options in ({"wrong_release":True},{"wrong_operation":True},
                        {"op":"rollback"}):
            with self.subTest(options=options):
                frame,data,parts=self.frame_v2(**options)
                proc=self.parked_client(frame,data)
                model=v2.BrokerV2(self.root)
                try:
                    with self.assertRaises((v1.Denied,signed.TrustRejected)):
                        model.approve_from_root_test_authority(*parts,proc.pid)
                finally:
                    model.close()
                reply=self.resume(proc)
                self.assertFalse(reply["ok"])
        self.assertEqual(self.ledger(),[])

    def test_07_root_approval_mismatch_modified_manifest_preserves_foreign_files(self):
        foreign=self.root/"public"/"recordings-iq.raw"
        foreign.write_bytes(b"RECORDING-NEVER-DELETE")
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        approval=self.root/"private"/"approval"/v2.BrokerV2.approval_name(
            json.loads(parts[2])["nonce"])
        before=approval.read_bytes()
        self.assertEqual(foreign.read_bytes(),b"RECORDING-NEVER-DELETE")
        self.assertTrue(self.resume(proc)["ok"])
        self.assertEqual(approval.read_bytes(),before)

    def test_08_after_release_crash_same_granted_ticket_retries_after_new_root_process(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_release")
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())
        self.start_server()
        reply=self.resume(proc)
        self.assertTrue(reply["ok"],reply)
        self.assertEqual(len(self.ledger()),1)
        self.assertEqual(self.active()["seq"],50)

    def test_09_after_prepare_crash_missing_blob_can_retry_without_foreign_deletion(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_prepare")
        self.assertEqual(self.ledger(),[])
        self.start_server()
        self.assertTrue(self.resume(proc)["ok"])
        self.assertEqual(self.active()["seq"],50)

    def test_10_foreign_release_without_signed_prepare_refused_and_preserved(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        release=self.root/"private"/"release"/(
            "rel-%020d-%s.bin"%(50,v2.dig(data)[:16]))
        self.stop_server()
        release.write_bytes(b"FOREIGN-DONT-DELETE")
        self.start_server()
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertIn("without protected prepare",reply["error"])
        self.assertEqual(release.read_bytes(),b"FOREIGN-DONT-DELETE")
        self.assertEqual(self.ledger(),[])

    def test_11_corrupted_authenticated_prepare_fails_closed_and_preserves_bytes(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts)
        receipt=self.root/"private"/"prepared"/"prep-00000000000000000050.json"
        raw=receipt.read_bytes()
        self.assertIn(b'"seq":50',raw)
        corrupt=raw.replace(b'"seq":50',b'"seq":51')
        receipt.write_bytes(corrupt) # privileged CI fault only
        self.start_server()
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertIn("unauthenticated",reply["error"])
        self.assertEqual(receipt.read_bytes(),corrupt)
        self.assertEqual(self.ledger(),[])

    def test_12_prepared_orphan_digest_changed_rejected_no_cleanup(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts)
        release=self.root/"private"/"release"/(
            "rel-%020d-%s.bin"%(50,v2.dig(data)[:16]))
        release.write_bytes(b"CHANGED-BY-ROOT-TEST")
        self.start_server()
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertIn("prepared orphan",reply["error"])
        self.assertEqual(release.read_bytes(),b"CHANGED-BY-ROOT-TEST")
        self.assertIsNone(self.active())

    def test_13_approved_transaction_replay_rejected_by_protected_journal(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.assertTrue(self.resume(proc)["ok"])
        stolen=self.request(frame,data)
        self.assertFalse(stolen["ok"])
        self.assertEqual(len(self.ledger()),1)

    def test_14_consecutive_manifest_specific_versions_preserve_old_release(self):
        frame,data,parts=self.frame_v2()
        p1=self.parked_client(frame,data)
        self.grant(p1,parts)
        self.assertTrue(self.resume(p1)["ok"])
        old=self.active()
        other=b"NEXT-BROKER-V2-SIGNED-ARTIFACT-51"
        frame,data,parts=self.frame_v2(
            seq=51,previous=old,data=other,source_commit="d"*40)
        p2=self.parked_client(frame,data)
        self.grant(p2,parts)
        self.assertTrue(self.resume(p2)["ok"])
        self.assertEqual([x["seq"] for x in self.ledger()],[50,51])
        self.assertEqual(self.active()["seq"],51)
        oldrel=self.root/"private"/"release"/old["release"]
        self.assertEqual(oldrel.read_bytes(),BLOB)

    def test_15_approved_parent_inherited_socket_child_does_not_inherit_approval(self):
        """SCM_CREDENTIALS is per MESSAGE, not stale creation SO_PEERCRED."""
        child_code = r"""
import array,fcntl,json,os,socket,sys
from pathlib import Path
sock=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
sock.settimeout(8)
sock.connect(sys.argv[1])
pid=os.fork()
if pid==0:
    try:
        data=Path(sys.argv[3]).read_bytes()
        raw=Path(sys.argv[2]).read_bytes()
        fd=os.memfd_create("inherited-v2",os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        os.write(fd,data)
        flags=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,flags)
        sock.sendmsg([raw],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[fd]))])
        os.close(fd)
        os._exit(0)
    except BaseException:
        os._exit(40)
_,status=os.waitpid(pid,0)
response=json.loads(sock.recv(4096))
print(json.dumps({"response":response,"child":pid,"status":status}),flush=True)
sock.close()
"""
        frame,data,parts=self.frame_v2()
        parent=self.parked_client(frame,data,code=child_code)
        self.grant(parent,parts)
        answer=self.resume(parent)
        self.assertEqual(answer["status"],0)
        self.assertFalse(answer["response"]["ok"])
        self.assertIsNone(self.active())

    def test_16_different_sender_same_uid_cannot_use_authentication_after_crash(self):
        frame,data,parts=self.frame_v2()
        authorized=self.parked_client(frame,data)
        self.grant(authorized,parts)
        self.stop_server()
        self.cut_as_approved(authorized,parts)
        self.start_server()
        other=self.request(frame,data)
        self.assertFalse(other["ok"])
        self.assertEqual(self.ledger(),[])
        self.assertTrue(self.resume(authorized)["ok"])


if __name__=="__main__":
    unittest.main(verbosity=2)
