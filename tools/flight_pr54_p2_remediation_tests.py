#!/usr/bin/env python3
"""Agent08 PR54 P2 negative acceptance, disposable GitHub-hosted Linux ONLY.

Real root broker subprocess, genuine exec'd UID65534 hostile socket clients.
Original Agent06 PR54 POSITIVE witnesses execute separately at exact QA SHA,
not rewritten to claim an old vulnerable model is secure. No real deployment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import unittest

from tools import flight_p1_broker_pr52_remediation_ci as v2
from tools import flight_p1_broker_os_boundary_ci as old
from tools import flight_p1_broker_pr52_remediation_tests as tests
from tools import flight_p1_broker_os_boundary_tests as linux

BLOB = linux.BLOB


@unittest.skipUnless(sys.platform == "linux", "Linux separate-UID acceptance")
class Agent08PR54P2NegativeAcceptance(unittest.TestCase):
    setUp = tests.PR52RemediationAcceptance.setUp
    start_server = tests.PR52RemediationAcceptance.start_server
    stop_server = tests.PR52RemediationAcceptance.stop_server
    frame_v2 = tests.PR52RemediationAcceptance.frame_v2
    reframe = staticmethod(tests.PR52RemediationAcceptance.reframe)
    parked_client = tests.PR52RemediationAcceptance.parked_client
    grant = tests.PR52RemediationAcceptance.grant
    resume = tests.PR52RemediationAcceptance.resume
    cut_as_approved = tests.PR52RemediationAcceptance.cut_as_approved
    sealed_fd = tests.PR52RemediationAcceptance.sealed_fd
    make_files = tests.PR52RemediationAcceptance.make_files
    request = tests.PR52RemediationAcceptance.request
    unpriv_action = tests.PR52RemediationAcceptance.unpriv_action
    active = tests.PR52RemediationAcceptance.active
    ledger = tests.PR52RemediationAcceptance.ledger

    def protected(self):
        model = v2.BrokerV2(self.root)
        self.addCleanup(model.close)
        return model

    def prep_file(self):
        return self.root/"private"/"prepared"/"prep-00000000000000000050.json"

    def blob_file(self, data=BLOB):
        return self.root/"private"/"release"/(
            "rel-%020d-%s.bin" % (50, v2.dig(data)[:16]))

    def handoff_file(self):
        return self.root/"private"/"handoff"/"transfer-00000000000000000050.json"

    def kill_original(self, p):
        os.kill(p.pid, signal.SIGKILL)
        p.wait(timeout=5)
        self.assertIsNotNone(p.returncode)

    def prepare_with_dead_original(self, cut="after_release"):
        frame,blob,parts=self.frame_v2()
        oldclient=self.parked_client(frame,blob)
        self.grant(oldclient,parts)
        self.stop_server()
        self.cut_as_approved(oldclient,parts,cut=cut)
        self.assertIsNone(self.active())
        self.assertEqual(self.ledger(),[])
        receipt=self.prep_file().read_bytes()
        self.kill_original(oldclient)
        return receipt,blob,parts

    def new_approved(self, **kwargs):
        frame,blob,parts=self.frame_v2(**kwargs)
        replacement=self.parked_client(frame,blob)
        self.grant(replacement,parts)
        return replacement,parts,blob

    def transfer(self, recipient, parts):
        b=self.protected()
        return b.authorize_takeover_from_root_test_authority(
            *parts,recipient.pid,now=old.CI_NOW)

    def test_01_REAL_UID_immediate_disconnect_cannot_kill_root_broker(self):
        self.assertIsNone(self.worker.poll())
        code = r"""
import socket,sys
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
s.connect(sys.argv[1])
s.shutdown(socket.SHUT_RDWR)
s.close()
print("DISCONNECTED",flush=True)
"""
        for _ in range(12):
            result=self.unpriv_action(code,self.sock)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn("DISCONNECTED",result.stdout)
        # Confirm accept loop still running, not just a delayed crash.
        frame,blob,parts=self.frame_v2()
        authorized=self.parked_client(frame,blob)
        self.grant(authorized,parts)
        self.assertTrue(self.resume(authorized)["ok"])
        self.assertIsNone(self.worker.poll())
        self.assertEqual(self.active()["seq"],50)

    def test_02_REAL_UID_malformed_disconnects_no_privilege_and_continuity(self):
        script=r"""
import socket,sys
for payload in (b"not-json",b"{",b""):
    s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    s.settimeout(4)
    s.connect(sys.argv[1])
    if payload: s.send(payload)
    s.shutdown(socket.SHUT_RDWR)
    s.close()
print("BAD_CONNECTIONS_CLOSED",flush=True)
"""
        result=self.unpriv_action(script,self.sock)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("BAD_CONNECTIONS_CLOSED",result.stdout)
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())
        frame,blob,parts=self.frame_v2()
        p=self.parked_client(frame,blob)
        self.grant(p,parts)
        self.assertTrue(self.resume(p)["ok"])
        self.assertIsNone(self.worker.poll())

    def test_03_REAL_UID_multiple_SCM_RIGHTS_and_shutdown_no_broker_termination(self):
        code=r"""
import array,os,fcntl,socket,sys
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
s.settimeout(4);s.connect(sys.argv[1])
a=os.memfd_create("multi-a",os.MFD_ALLOW_SEALING)
b=os.memfd_create("multi-b",os.MFD_ALLOW_SEALING)
s.sendmsg([b'not-json'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[a,b]))])
s.shutdown(socket.SHUT_RDWR)
s.close();os.close(a);os.close(b)
print("MULTIPLE_FD_DENIED",flush=True)
"""
        cp=self.unpriv_action(code,self.sock)
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertIn("MULTIPLE_FD_DENIED",cp.stdout)
        self.assertEqual(self.ledger(),[])
        frame,blob,parts=self.frame_v2()
        legit=self.parked_client(frame,blob)
        self.grant(legit,parts)
        self.assertTrue(self.resume(legit)["ok"])
        self.assertIsNone(self.worker.poll())

    def test_04_anonymous_stolen_ticket_still_denied_after_disconnect_storm(self):
        code="import socket,sys;s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);s.connect(sys.argv[1]);s.close()"
        for _ in range(5):
            self.assertEqual(self.unpriv_action(code,self.sock).returncode,0)
        frame,blob,_=self.frame_v2()
        result=self.request(frame,blob)
        self.assertFalse(result["ok"])
        self.assertIn("root-side",result["error"])
        self.assertIsNone(self.active())
        self.assertIsNone(self.worker.poll())

    def test_05_REAL_UID_original_dies_after_release_new_approval_and_transfer_works(self):
        receipt,blob,parts=self.prepare_with_dead_original(cut="after_release")
        old_file=self.blob_file()
        old_stat=old_file.stat()
        old_bytes=old_file.read_bytes()
        replacement,parts2,_=self.new_approved()
        handoff=self.transfer(replacement,parts2)
        self.assertEqual(handoff["prepared_hash"],v2.dig(receipt))
        self.assertNotEqual(handoff["from_pid"],handoff["to_pid"])
        self.assertTrue(self.handoff_file().exists())
        self.start_server()
        reply=self.resume(replacement)
        self.assertTrue(reply["ok"],reply)
        self.assertEqual(self.active()["seq"],50)
        self.assertEqual(self.blob_file().read_bytes(),old_bytes)
        self.assertEqual(self.blob_file().stat().st_ino,old_stat.st_ino)
        self.assertEqual(self.prep_file().read_bytes(),receipt)
        self.assertEqual(len(self.ledger()),1)

    def test_06_REAL_UID_original_dies_after_prepare_new_approval_resumes_without_unlink(self):
        original,blob,_=self.prepare_with_dead_original(cut="after_prepare")
        self.assertFalse(self.blob_file().exists())
        replacement,parts,_=self.new_approved()
        self.transfer(replacement,parts)
        self.start_server()
        result=self.resume(replacement)
        self.assertTrue(result["ok"],result)
        self.assertEqual(self.blob_file().read_bytes(),BLOB)
        self.assertEqual(self.prep_file().read_bytes(),original)
        self.assertEqual(self.active()["seq"],50)

    def test_07_dead_original_new_bearer_no_root_handoff_stays_fail_closed(self):
        prepared,blob,_=self.prepare_with_dead_original()
        replacement,parts,_=self.new_approved()
        self.start_server()
        response=self.resume(replacement)
        self.assertFalse(response["ok"])
        self.assertIn("independent protected transfer",response["error"])
        self.assertEqual(self.prep_file().read_bytes(),prepared)
        self.assertEqual(self.blob_file().read_bytes(),blob)
        self.assertEqual(self.ledger(),[])

    def test_08_live_original_prohibits_transfer_and_original_can_continue(self):
        frame,blob,parts=self.frame_v2()
        original=self.parked_client(frame,blob)
        self.grant(original,parts)
        self.stop_server()
        self.cut_as_approved(original,parts,cut="after_release")
        replacement,parts2,_=self.new_approved()
        with self.assertRaisesRegex(old.Denied,"still alive"):
            self.transfer(replacement,parts2)
        self.assertFalse(self.handoff_file().exists())
        self.start_server()
        self.assertFalse(self.resume(replacement)["ok"])
        self.assertTrue(self.resume(original)["ok"])
        self.assertEqual(self.active()["seq"],50)

    def test_09_died_original_new_client_without_root_approval_cannot_transfer(self):
        receipt,blob,_=self.prepare_with_dead_original()
        frame,blob2,parts=self.frame_v2()
        client=self.parked_client(frame,blob2)
        b=self.protected()
        with self.assertRaisesRegex(old.Denied,"missing separate root-side"):
            b.authorize_takeover_from_root_test_authority(
                *parts,client.pid,now=old.CI_NOW)
        self.assertFalse(self.handoff_file().exists())
        self.start_server()
        self.assertFalse(self.resume(client)["ok"])
        self.assertEqual(self.prep_file().read_bytes(),receipt)

    def test_10_different_legitimately_signed_source_manifest_cannot_transfer(self):
        original,blob,_=self.prepare_with_dead_original()
        newproc,parts,_=self.new_approved(source_commit="c"*40)
        with self.assertRaisesRegex(old.Denied,"would change original signed manifest"):
            self.transfer(newproc,parts)
        self.assertFalse(self.handoff_file().exists())
        self.assertEqual(self.prep_file().read_bytes(),original)
        self.assertEqual(self.blob_file().read_bytes(),blob)

    def test_11_bogus_MAC_prepared_record_denied_and_preserved(self):
        original,blob,_=self.prepare_with_dead_original()
        damaged=original.replace(b'"seq":50',b'"seq":51')
        self.assertNotEqual(damaged,original)
        self.prep_file().write_bytes(damaged)
        newproc,parts,_=self.new_approved()
        with self.assertRaisesRegex(old.Denied,"unauthenticated"):
            self.transfer(newproc,parts)
        self.assertFalse(self.handoff_file().exists())
        self.assertEqual(self.prep_file().read_bytes(),damaged)
        self.assertEqual(self.blob_file().read_bytes(),blob)

    def test_12_modified_orphan_bytes_cannot_transfer_and_are_not_deleted(self):
        original,blob,_=self.prepare_with_dead_original()
        tampered=b"FOREIGN-AFTER-CRASH-DO-NOT-DELETE"
        self.blob_file().write_bytes(tampered)  # root CI-only fault injection
        newproc,parts,_=self.new_approved()
        with self.assertRaisesRegex(old.Denied,"altered orphan"):
            self.transfer(newproc,parts)
        self.assertFalse(self.handoff_file().exists())
        self.assertEqual(self.blob_file().read_bytes(),tampered)
        self.assertEqual(self.prep_file().read_bytes(),original)

    def test_13_REAL_UID_cannot_forge_protected_handoff_record(self):
        _,blob,_=self.prepare_with_dead_original()
        target=self.handoff_file()
        cp=self.unpriv_action("from pathlib import Path;import sys;"
                              "Path(sys.argv[1]).write_bytes(b'FAKE_TRANSFER')",target)
        self.assertNotEqual(cp.returncode,0)
        self.assertIn("PermissionError",cp.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(self.ledger(),[])

    def test_14_forged_existing_handoff_record_rejected_without_overwrite(self):
        original,blob,_=self.prepare_with_dead_original()
        foreign=b"FORGED-ROOT-FIXTURE-NEVER-ERASE"
        self.handoff_file().write_bytes(foreign)
        newproc,parts,_=self.new_approved()
        with self.assertRaises((old.Denied,ValueError)):
            self.transfer(newproc,parts)
        self.assertEqual(self.handoff_file().read_bytes(),foreign)
        self.assertEqual(self.prep_file().read_bytes(),original)
        self.assertEqual(self.blob_file().read_bytes(),blob)

    def test_15_second_distinct_root_approved_recipient_denied_after_handoff(self):
        original,blob,_=self.prepare_with_dead_original()
        authorized,parts,_=self.new_approved()
        first=self.transfer(authorized,parts)
        firstraw=self.handoff_file().read_bytes()
        other,partstwo,_=self.new_approved()
        with self.assertRaisesRegex(old.Denied,"different/foreign transfer"):
            self.transfer(other,partstwo)
        self.assertEqual(self.handoff_file().read_bytes(),firstraw)
        self.assertEqual(self.prep_file().read_bytes(),original)
        self.start_server()
        self.assertFalse(self.resume(other)["ok"])
        self.assertTrue(self.resume(authorized)["ok"])
        self.assertEqual(self.active()["seq"],50)

    def test_16_exact_transfer_authority_reissue_is_idempotent(self):
        original,blob,_=self.prepare_with_dead_original()
        newproc,parts,_=self.new_approved()
        one=self.transfer(newproc,parts)
        bytes_before=self.handoff_file().read_bytes()
        two=self.transfer(newproc,parts)
        self.assertEqual(one,two)
        self.assertEqual(self.handoff_file().read_bytes(),bytes_before)
        self.start_server()
        self.assertTrue(self.resume(newproc)["ok"])
        self.assertEqual(len(self.ledger()),1)

    def test_17_original_unchanged_live_client_retry_preserves_v2_semantics(self):
        frame,blob,parts=self.frame_v2()
        orig=self.parked_client(frame,blob)
        self.grant(orig,parts)
        self.stop_server()
        self.cut_as_approved(orig,parts,cut="after_release")
        self.assertFalse(self.handoff_file().exists())
        self.start_server()
        self.assertTrue(self.resume(orig)["ok"])
        self.assertEqual(self.active()["seq"],50)
        self.assertFalse(self.handoff_file().exists())

    def test_18_malformed_IPC_transfer_command_exposes_no_root_approval_action(self):
        code=r"""
import socket,sys
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
s.settimeout(5);s.connect(sys.argv[1])
s.send(b'{"action":"transfer","root_approve":true}')
print(s.recv(2048).decode(),flush=True)
s.close()
"""
        cp=self.unpriv_action(code,self.sock)
        self.assertEqual(cp.returncode,0,cp.stderr)
        message=json.loads(cp.stdout)
        self.assertFalse(message["ok"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())
        self.assertIsNone(self.worker.poll())


if __name__=="__main__":
    unittest.main(verbosity=2)
