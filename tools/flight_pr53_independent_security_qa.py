#!/usr/bin/env python3
"""Agent 06 independent PR53 broker-v2 adversarial QA.

FROZEN target: b68b248e6d9b22c00ea8695e975c7f40bd27866a
FROZEN positive attack witnesses: QA PR52 f13d8e00afdcad276611cba31d1bef57986ba877
Real ephemeral Linux runner ROOT broker versus exec'd UID65534 clients.
No live service, no user host, no SDR, no installation, no production signer.
Deliberate POSITIVE_LIMIT tests expose where signature checks are NOT user consent.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import unittest
import array

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import flight_p1_broker_pr52_remediation_ci as v2
from tools import flight_p1_broker_pr52_remediation_tests as author
from tools import flight_p1_broker_os_boundary_ci as old
from tools import flight_p1_broker_os_boundary_tests as native
from tools import flight_signed_installer_ci_prototype as signed

NOW=old.CI_NOW
UID=native.UNPRIV
DATA=native.BLOB


@unittest.skipUnless(sys.platform=="linux","Linux kernel UID enforcement only")
class Agent06IndependentPR53QA(unittest.TestCase):
    # Reuse only the immutable disposable Linux fixture process wiring,
    # NOT previous test methods or their security assertions.
    setUp=author.PR52RemediationAcceptance.setUp
    start_server=author.PR52RemediationAcceptance.start_server
    stop_server=author.PR52RemediationAcceptance.stop_server
    frame_v2=author.PR52RemediationAcceptance.frame_v2
    reframe=staticmethod(author.PR52RemediationAcceptance.reframe)
    parked_client=author.PR52RemediationAcceptance.parked_client
    grant=author.PR52RemediationAcceptance.grant
    resume=author.PR52RemediationAcceptance.resume
    sealed_fd=author.PR52RemediationAcceptance.sealed_fd
    cut_as_approved=author.PR52RemediationAcceptance.cut_as_approved
    make_files=native.RealUIDBrokerTests.make_files
    request=native.RealUIDBrokerTests.request
    unpriv_action=native.RealUIDBrokerTests.unpriv_action
    active=native.RealUIDBrokerTests.active
    ledger=native.RealUIDBrokerTests.ledger

    def open_broker(self):
        b=v2.BrokerV2(self.root)
        self.addCleanup(b.close)
        return b

    def prep_path(self,seq=50):
        return self.root/"private"/"prepared"/("prep-%020d.json"%seq)

    def release_path(self,seq,data):
        return self.root/"private"/"release"/(
            "rel-%020d-%s.bin"%(seq,hashlib.sha256(data).hexdigest()[:16]))

    def test_01_kernel_two_uids_and_real_protected_grant_root(self):
        self.assertEqual(os.geteuid(),0)
        cp=self.unpriv_action("import os; print(os.getuid(),os.geteuid())")
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertEqual(cp.stdout.strip(),f"{UID} {UID}")
        for n in ("approval","prepared","trust","journal","active","release"):
            path=self.root/"private"/n
            self.assertEqual(path.stat().st_uid,0)
            self.assertEqual(path.stat().st_mode&0o777,0o700)
        self.assertEqual(self.ledger(),[])

    def test_02_stolen_unused_valid_ticket_never_self_approves(self):
        frame,data,_=self.frame_v2()
        attacker=self.request(frame,data)
        self.assertFalse(attacker["ok"])
        self.assertIn("root-side",attacker["error"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_03_stolen_ticket_other_real_same_uid_pid_denied_while_grant_unused(self):
        frame,data,parts=self.frame_v2()
        approved=self.parked_client(frame,data)
        record=self.grant(approved,parts)
        self.assertEqual(record["pid"],approved.pid)
        attacked=self.request(frame,data)
        self.assertFalse(attacked["ok"])
        self.assertIn("not bound to this sender",attacked["error"])
        self.assertIsNone(self.active())
        actual=self.resume(approved)
        self.assertTrue(actual["ok"],actual)
        self.assertEqual(self.active()["seq"],50)

    def test_04_unprivileged_spoof_of_root_grant_and_private_policy_denied_by_DAC(self):
        frame,data,parts=self.frame_v2()
        nonce=json.loads(parts[2])["nonce"]
        targets=[
            self.root/"private"/"approval"/v2.BrokerV2.approval_name(nonce),
            self.root/"private"/"trust"/"pins.json",
            self.root/"private"/"trust"/"ledger.key",
            self.root/"private"/"prepared"/v2.BrokerV2.prepared_name(50),
        ]
        for target in targets:
            cp=self.unpriv_action(
                "from pathlib import Path;import sys;"
                "Path(sys.argv[1]).write_bytes(b'FORGED-ROOT-GRANT')",target)
            self.assertNotEqual(cp.returncode,0,target)
            self.assertIn("PermissionError",cp.stderr)
        self.assertFalse(self.request(frame,data)["ok"])

    def test_05_root_grant_HMAC_corruption_fail_closed_preserving_foreign(self):
        foreign=self.root/"public"/"recording-iq.raw"
        foreign.write_bytes(b"FOREIGN-RECORDING-PRESERVE")
        frame,data,parts=self.frame_v2()
        pid=self.parked_client(frame,data)
        self.grant(pid,parts)
        name=v2.BrokerV2.approval_name(json.loads(parts[2])["nonce"])
        path=self.root/"private"/"approval"/name
        original=path.read_bytes()
        forged=original.replace(b'"seq":50',b'"seq":51')
        self.assertNotEqual(forged,original)
        path.write_bytes(forged)   # ROOT fault injection on disposable CI ONLY
        result=self.resume(pid)
        self.assertFalse(result["ok"])
        self.assertIn("unauthenticated",result["error"])
        self.assertEqual(path.read_bytes(),forged)
        self.assertEqual(foreign.read_bytes(),b"FOREIGN-RECORDING-PRESERVE")
        self.assertIsNone(self.active())

    def test_06_authentic_root_mac_with_wrong_pid_start_ticks_denied(self):
        frame,data,parts=self.frame_v2()
        approved=self.parked_client(frame,data)
        self.grant(approved,parts)
        broker=self.open_broker()
        name=v2.BrokerV2.approval_name(json.loads(parts[2])["nonce"])
        path=self.root/"private"/"approval"/name
        original=broker.verify_record(path.read_bytes(),v2.APPROVAL_FIELDS)
        changed=dict(original,start_ticks=original["start_ticks"]+1)
        # ROOT test fixture creates AUTHENTIC HMAC but FORGED PID epoch.
        # This is a start-ticks negative control, not a real PID-reuse test.
        path.write_bytes(broker.signed_record(changed))
        answer=self.resume(approved)
        self.assertFalse(answer["ok"])
        self.assertIn("not bound to this sender",answer["error"])
        self.assertIsNone(self.active())

    def test_07_root_approval_rejects_pid_that_exited_before_issuance(self):
        frame,data,parts=self.frame_v2()
        gone=self.parked_client(frame,data)
        os.kill(gone.pid,signal.SIGKILL)
        gone.wait(timeout=4)
        broker=self.open_broker()
        with self.assertRaisesRegex(old.Denied,"sender process no longer"):
            broker.approve_from_root_test_authority(*parts,gone.pid,now=NOW)
        self.assertEqual(self.ledger(),[])

    def test_08_inherited_SOCKET_with_approved_parent_not_sender_child(self):
        code=r"""
import array,fcntl,json,os,socket,sys
from pathlib import Path
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
s.settimeout(8)
s.connect(sys.argv[1])
release_r,release_w=os.pipe()
child=os.fork()
if child==0:
  os.close(release_w)
  try:
    data=Path(sys.argv[3]).read_bytes()
    frame=Path(sys.argv[2]).read_bytes()
    fd=os.memfd_create("agent06-child",os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    os.write(fd,data)
    flags=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SEAL
    fcntl.fcntl(fd,fcntl.F_ADD_SEALS,flags)
    s.sendmsg([frame],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[fd]))])
    os.close(fd)
    os.read(release_r,1)  # keep the actual SENDER PID alive for /proc verification
    os._exit(0)
  except BaseException:
    os._exit(42)
os.close(release_r)
ans=json.loads(s.recv(4096))
os.write(release_w,b"x")
os.close(release_w)
_,status=os.waitpid(child,0)
print(json.dumps({"response":ans,"child":child,"status":status}),flush=True)
s.close()
"""
        frame,data,parts=self.frame_v2()
        approved_parent=self.parked_client(frame,data,code=code)
        self.grant(approved_parent,parts)
        result=self.resume(approved_parent)
        self.assertEqual(result["status"],0)
        self.assertFalse(result["response"]["ok"])
        self.assertIn("not bound to this sender",result["response"]["error"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_09_independent_signed_manifest_commit_swap_denied_with_valid_signatures(self):
        frame,data,(manifest,msig,ticket,tsig)=self.frame_v2()
        altered=dict(json.loads(manifest),source_commit="c"*40)
        raw=signed.canonical_bytes(altered)
        other_sig=self.release_key.sign(signed.DOMAIN+raw)
        signed.verify_metadata(raw,other_sig,
            {"test-root":native.pub(self.release_key)},
            expected_platform="linux",expected_arch="x86_64",
            minimum_sequence=0,now=NOW)
        self.assertNotEqual(v2.dig(manifest),v2.dig(raw))
        altered_frame=self.reframe((raw,other_sig,ticket,tsig))
        approved=self.parked_client(altered_frame,data)
        self.grant(approved,(manifest,msig,ticket,tsig))
        result=self.resume(approved)
        self.assertFalse(result["ok"])
        self.assertIn("exact signed manifest",result["error"])
        self.assertIsNone(self.active())

    def test_10_ticket_signature_hash_and_field_mutation_denied(self):
        frame,data,parts=self.frame_v2()
        original=json.loads(parts[2])
        for field,value in [
            ("manifest_sha256","0"*64),
            ("release_signature_sha256","1"*64),
            ("source_commit","c"*40),
            ("digest","2"*64),
            ("sequence",51),
        ]:
            with self.subTest(field=field):
                ticket=old.canonical(dict(original,**{field:value}))
                changed=self.reframe((parts[0],parts[1],ticket,parts[3]))
                result=self.request(changed,data)
                self.assertFalse(result["ok"])
        self.assertEqual(self.ledger(),[])

    def test_11_root_signed_approval_still_binds_exact_ticket_signature_identity(self):
        frame,data,parts=self.frame_v2()
        authorized=self.parked_client(frame,data)
        self.grant(authorized,parts)
        # The original ticket and release signature remain legitimate.
        # Different nonce requires a DIFFERENT signed operation ticket.
        frame2,data2,parts2=self.frame_v2(nonce="f"*32)
        bad=self.request(frame2,data2)
        self.assertFalse(bad["ok"])
        self.assertIsNone(self.active())
        self.assertTrue(self.resume(authorized)["ok"])

    def test_12_valid_alternative_source_manifest_with_new_signed_ticket_still_needs_own_grant(self):
        f,data,parts=self.frame_v2()
        approved=self.parked_client(f,data)
        self.grant(approved,parts)
        another_frame,another_data,another_parts=self.frame_v2(source_commit="d"*40)
        attacker=self.request(another_frame,another_data)
        self.assertFalse(attacker["ok"])
        self.assertIsNone(self.active())
        self.assertTrue(self.resume(approved)["ok"])

    def test_13_duplicate_nonce_cannot_be_approved_twice_by_root(self):
        frame,data,parts=self.frame_v2()
        authorized=self.parked_client(frame,data)
        self.grant(authorized,parts)
        broker=self.open_broker()
        with self.assertRaises(FileExistsError):
            broker.approve_from_root_test_authority(*parts,authorized.pid,now=NOW)
        self.assertTrue(self.resume(authorized)["ok"])
        self.assertEqual(len(self.ledger()),1)

    def test_14_manifest_size_or_bytes_mismatch_refused_even_with_approved_ticket(self):
        frame,data,parts=self.frame_v2()
        approved=self.parked_client(frame,data[:-1])
        self.grant(approved,parts)
        result=self.resume(approved)
        self.assertFalse(result["ok"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_15_SCM_RIGHTS_multi_descriptor_malformed_rejected_and_closed(self):
        l,r=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        r.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
        frame,data,_=self.frame_v2()
        left=os.memfd_create("independent-left",os.MFD_ALLOW_SEALING)
        right=os.memfd_create("independent-right",os.MFD_ALLOW_SEALING)
        try:
            for fd in (left,right):
                os.write(fd,data)
                fcntl.fcntl(fd,fcntl.F_ADD_SEALS,old.REQUIRED_SEALS)
            with l,r:
                l.sendmsg([frame],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,
                                   array.array("i",[left,right]))])
                with self.assertRaisesRegex(old.Denied,"exactly one FD"):
                    v2.receive_v2(r)
        finally:
            os.close(left)
            os.close(right)
        self.assertEqual(self.ledger(),[])

    def test_16_PREPARED_receipt_mac_corrupted_preserved_fail_closed(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_release")
        receipt=self.prep_path()
        orig=receipt.read_bytes()
        corrupt=orig.replace(b'"seq":50',b'"seq":51')
        self.assertNotEqual(orig,corrupt)
        receipt.write_bytes(corrupt)
        self.start_server()
        result=self.resume(proc)
        self.assertFalse(result["ok"])
        self.assertIn("unauthenticated",result["error"])
        self.assertEqual(receipt.read_bytes(),corrupt)
        self.assertIsNone(self.active())

    def test_17_prepared_authentic_receipt_matches_but_foreign_byte_corruption_denied(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_release")
        target=self.release_path(50,data)
        self.assertEqual(target.read_bytes(),data)
        target.write_bytes(b"FOREIGN-ALTERED-DATA")
        self.start_server()
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertIn("prepared orphan",reply["error"])
        self.assertEqual(target.read_bytes(),b"FOREIGN-ALTERED-DATA")
        self.assertIsNone(self.active())

    def test_18_missing_prepare_receipt_keeps_unknown_release_without_publishing(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        target=self.release_path(50,data)
        target.write_bytes(b"FOREIGN-UNOWNED-RELEASE")
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertIn("without protected prepare",reply["error"])
        self.assertEqual(target.read_bytes(),b"FOREIGN-UNOWNED-RELEASE")
        self.assertIsNone(self.active())

    def test_19_after_release_exact_retry_new_root_process_valid_and_non_destructive(self):
        foreign=self.root/"public"/"user-recording.wav"
        foreign.write_bytes(b"RECORDING-KEEP")
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_release")
        self.assertEqual(self.ledger(),[])
        self.assertEqual(self.release_path(50,data).read_bytes(),data)
        self.assertTrue(self.prep_path().is_file())
        self.start_server()
        result=self.resume(proc)
        self.assertTrue(result["ok"],result)
        self.assertEqual(self.active()["seq"],50)
        self.assertEqual(self.ledger()[0]["manifest_hash"],v2.dig(parts[0]))
        self.assertEqual(foreign.read_bytes(),b"RECORDING-KEEP")

    def test_20_after_prepare_exact_retry_new_root_process_valid_without_old_blob(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_prepare")
        self.assertTrue(self.prep_path().is_file())
        self.assertFalse(self.release_path(50,data).exists())
        self.start_server()
        result=self.resume(proc)
        self.assertTrue(result["ok"],result)
        self.assertEqual(self.active()["seq"],50)

    def test_21_crash_AFTER_journal_recovery_never_reuses_ticket_to_create_duplicate(self):
        frame,data,parts=self.frame_v2()
        proc=self.parked_client(frame,data)
        self.grant(proc,parts)
        self.stop_server()
        self.cut_as_approved(proc,parts,cut="after_journal")
        self.start_server()
        self.assertEqual(self.active()["seq"],50)
        reply=self.resume(proc)
        self.assertFalse(reply["ok"])
        self.assertEqual(len(self.ledger()),1)
        self.assertEqual(self.active()["seq"],50)

    def test_22_POSITIVE_LIMIT_root_grant_not_real_human_or_independent_OS_consent(self):
        """ROOT CI authority can issue a valid grant for any live UID65534
        process without evidence of end-user approval. This positive
        construction illustrates remaining P1 POLICY/HUMAN consent HOLD.
        """
        frame,data,parts=self.frame_v2()
        process=self.parked_client(frame,data)
        # No polkit/user prompt/consent source is consulted by this root API.
        record=self.grant(process,parts)
        self.assertEqual(record["pid"],process.pid)
        reply=self.resume(process)
        self.assertTrue(reply["ok"],reply)
        self.assertEqual(self.active()["seq"],50)


    def test_23_POSITIVE_LIMIT_client_death_after_release_blocks_fresh_independently_granted_retry(self):
        """P2 recovery/liveness gap, NOT auth bypass. Broker's protected
        prepare is irrevocably bound to old ticket hash+nonce and original
        PROCESS grant. A killed approved client cannot retry. A distinct new
        UID65534 client obtains its OWN correctly root-approved signed
        operation and cannot adopt the orphan under the same sequence.
        Safe fail-closed; operational progress requires an explicit
        owner-authorized prepare-transfer/cancel state machine.
        """
        frame,data,parts=self.frame_v2()
        initial=self.parked_client(frame,data)
        self.grant(initial,parts)
        self.stop_server()
        self.cut_as_approved(initial,parts,cut="after_release")
        oldreceipt=self.prep_path().read_bytes()
        oldblob=self.release_path(50,data).read_bytes()
        os.kill(initial.pid,signal.SIGKILL)
        initial.wait(timeout=5)
        self.start_server()
        replacement_frame,replacement_data,replacement_parts=self.frame_v2()
        replacement=self.parked_client(replacement_frame,replacement_data)
        self.grant(replacement,replacement_parts)
        result=self.resume(replacement)
        self.assertFalse(result["ok"],result)
        self.assertIn("mismatched authenticated prepare receipt",result["error"])
        self.assertEqual(self.prep_path().read_bytes(),oldreceipt)
        self.assertEqual(self.release_path(50,data).read_bytes(),oldblob)
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_24_POSITIVE_LIMIT_client_death_after_prepare_blocks_fresh_authorized_attempt(self):
        """Even after_prepare BEFORE the release file exists, a new root
        approval and new ticket cannot displace old signed prepare safely.
        This is correct foreign-preservation behavior but leaves no
        progress/recovery path once initial PID has died.
        """
        frame,data,parts=self.frame_v2()
        previous=self.parked_client(frame,data)
        self.grant(previous,parts)
        self.stop_server()
        self.cut_as_approved(previous,parts,cut="after_prepare")
        initialprep=self.prep_path().read_bytes()
        self.assertFalse(self.release_path(50,data).exists())
        os.kill(previous.pid,signal.SIGKILL)
        previous.wait(timeout=5)
        self.start_server()
        newframe,newblob,newparts=self.frame_v2()
        newproc=self.parked_client(newframe,newblob)
        self.grant(newproc,newparts)
        result=self.resume(newproc)
        self.assertFalse(result["ok"])
        self.assertIn("mismatched authenticated prepare receipt",result["error"])
        self.assertEqual(self.prep_path().read_bytes(),initialprep)
        self.assertFalse(self.release_path(50,data).exists())
        self.assertIsNone(self.active())

    def test_25_kernel_rejects_explicit_forged_SCM_CREDENTIALS_for_approved_PID(self):
        """Actual UID65534 sender tries to send SCM_CREDENTIALS claiming
        DIFFERENT already-approved PID. Kernel rejects impersonation without
        privileged capabilities. This is kernel negative, not Python mock.
        """
        frame,data,parts=self.frame_v2()
        approved=self.parked_client(frame,data)
        self.grant(approved,parts)
        f,blob=self.make_files(frame,data)
        code=r"""
import array,fcntl,os,socket,struct,sys
from pathlib import Path
sock=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
sock.settimeout(5)
sock.connect(sys.argv[1])
fd=os.memfd_create("forge-credentials",os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
os.write(fd,Path(sys.argv[3]).read_bytes())
fl=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fl)
claims=struct.pack("3i",int(sys.argv[4]),os.getuid(),os.getgid())
try:
  sock.sendmsg([Path(sys.argv[2]).read_bytes()],
      [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[fd])),
       (socket.SOL_SOCKET,socket.SCM_CREDENTIALS,claims)])
  print("FORGED_CREDENTIALS_UNEXPECTEDLY_ACCEPTED")
except PermissionError:
  print("KERNEL_REJECTED_FORGED_PID")
finally:
  sock.close()
  os.close(fd)
"""
        result=self.unpriv_action(code,self.sock,f,blob,approved.pid)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("KERNEL_REJECTED_FORGED_PID",result.stdout)
        self.assertIsNone(self.active())
        self.assertEqual(self.ledger(),[])
        # A closed malformed client may also terminate this disposable
        # broker. That availability defect is independently tested in #26.


    def test_26_POSITIVE_GAP_ordinary_unprivileged_disconnect_crashes_root_broker(self):
        """Independently identified P2 availability attack against the
        EPHEMERAL CI V2 server: even without ticket, SCM_RIGHTS or any
        signing key, UID65534 can connect then shutdown its socket.
        server() catches receive exceptions but its conn.sendall(reply)
        lies OUTSIDE that exception handler. BrokenPipeError exits the
        privileged test-broker process. A GREEN POSITIVE test means the
        denial-of-service was REPRODUCED, not remediated.
        """
        self.assertIsNone(self.worker.poll())
        code=r"""
import socket,sys
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
s.settimeout(4)
s.connect(sys.argv[1])
s.shutdown(socket.SHUT_RDWR)
s.close()
print("UNPRIVILEGED_DISCONNECTED",flush=True)
"""
        cp=self.unpriv_action(code,self.sock)
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertIn("UNPRIVILEGED_DISCONNECTED",cp.stdout)
        self.worker.wait(timeout=5)
        self.assertIsNotNone(self.worker.returncode)
        stderr=self.worker.stderr.read()
        self.assertIn("BrokenPipeError",stderr)
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())


if __name__=="__main__":
    unittest.main(verbosity=2)
