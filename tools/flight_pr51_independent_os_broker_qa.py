#!/usr/bin/env python3
"""Agent06 PR51 independent OS broker security audit — QA ONLY.

Real Ubuntu runner tests, UID0 privileged disposable subprocess, independently
exec'd UID65534 adversarial client. No installed service, production signing
keys, owner device, external hardware or filesystem access outside unique
temporary root-owned /tmp/flight-agent08- test fixtures.

POSITIVE_LIMIT cases deliberately accept an unsafe protocol property: a
successful test is evidence of the *gap*, not a security clearance.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import flight_p1_broker_os_boundary_ci as broker
from tools import flight_p1_broker_os_boundary_tests as original
from tools import flight_signed_installer_ci_prototype as signed

NOW=broker.CI_NOW
UNPRIV=65534
BLOB=original.BLOB

# This is NOT a subclass of the 20 original tests. Reuse only their isolated
# provision/start/stop/client wiring to test the committed broker code with
# independently authored adversarial controls. The original suites are run
# separately, untouched, in the same CI.
@unittest.skipUnless(sys.platform=="linux", "Real Linux OS boundary only")
class IndependentPR51BrokerQA(unittest.TestCase):
    setUp=original.RealUIDBrokerTests.setUp
    start_server=original.RealUIDBrokerTests.start_server
    stop_server=original.RealUIDBrokerTests.stop_server
    payload=original.RealUIDBrokerTests.payload
    make_files=original.RealUIDBrokerTests.make_files
    request=original.RealUIDBrokerTests.request
    unpriv_action=original.RealUIDBrokerTests.unpriv_action
    active=original.RealUIDBrokerTests.active
    ledger=original.RealUIDBrokerTests.ledger

    def _root_model(self):
        b=broker.Broker(self.root)
        self.addCleanup(b.close)
        return b

    def _release_path(self, seq, data):
        return self.root/"private"/"release"/(
            "rel-%020d-%s.bin" % (seq,hashlib.sha256(data).hexdigest()[:16]))

    def test_01_REAL_UID_kernel_disallows_trust_policy_and_journal_modification(self):
        self.assertEqual(os.geteuid(),0)
        self.assertEqual(self.root.stat().st_uid,0)
        for path in (
            self.root/"private"/"trust"/"pins.json",
            self.root/"private"/"trust"/"ledger.key",
            self.root/"private"/"lock"/"transaction.lock",
            self.root/"private"/"journal"/"txn-00000000000000000050.json",
            self.root/"private"/"active"/"active.json",
        ):
            cp=self.unpriv_action(
                "from pathlib import Path;import sys;"
                "p=Path(sys.argv[1]);"
                "p.write_bytes(b'ATTACK')",path)
            self.assertNotEqual(cp.returncode,0,path)
            self.assertIn("PermissionError",cp.stderr)
        self.assertIsNone(self.active())
        self.assertEqual(self.ledger(),[])
        self.assertEqual((self.root/"private"/"trust"/"pins.json").stat().st_uid,0)

    def test_02_REAL_UID_cannot_swap_root_owned_namespace_or_symlink_ancestor(self):
        outside=self.root/"public"/"unrelated-recordings.iq"
        outside.write_bytes(b"FOREIGN KEEP EXACT")
        actions=[
            ("import os,sys;os.rename(sys.argv[1],sys.argv[2])",
             (self.root,"/tmp/flight-stolen-by-uid65534")),
            ("import os,sys;os.unlink(sys.argv[1])",
             (self.root/"private"/"trust"/"pins.json",)),
            ("import os,sys;os.symlink(sys.argv[2],sys.argv[1])",
             (self.root/"private"/"active"/"active.json",outside)),
        ]
        for code,args in actions:
            cp=self.unpriv_action(code,*args)
            self.assertNotEqual(cp.returncode,0)
        self.assertEqual(outside.read_bytes(),b"FOREIGN KEEP EXACT")
        self.assertTrue(self.root.exists())
        self.assertIsNone(self.active())

    def test_03_REAL_UID_cannot_clone_known_test_key_authority(self):
        # Same-UID app can mint a forged release/op pair, but root-protected
        # public authority is fixed independently of caller-provided pins.
        attacker=Ed25519PrivateKey.generate()
        frame,data,_=self.payload(bad_release_key=attacker)
        ans=self.request(frame,data)
        self.assertFalse(ans["ok"])
        self.assertEqual(self.ledger(),[])
        frame,data,_=self.payload(bad_operation_key=attacker)
        ans=self.request(frame,data)
        self.assertFalse(ans["ok"])
        self.assertEqual(self.ledger(),[])

    def test_04_missing_or_wrong_ticket_cannot_approve_privileged_activation(self):
        for op in ("rollback","install","uninstall"):
            frame,blob,_=self.payload(op=op)
            result=self.request(frame,blob)
            self.assertFalse(result["ok"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_05_inherited_socket_child_sender_without_ticket_rejected(self):
        # Separate real UID65534 process creates broker connection, forks a
        # CHILD which sends FD. SO_PEERCRED cannot determine actual human
        # intent; a WRONG signed operation ticket must still reject.
        frame,data,_=self.payload(bad_operation_key=Ed25519PrivateKey.generate())
        f,artifact=self.make_files(frame,data)
        code=r"""
import array,fcntl,os,socket,sys,json
from pathlib import Path
sock=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
sock.settimeout(8)
sock.connect(sys.argv[1])
initiator=os.getpid()
pid=os.fork()
if pid==0:
    try:
        data=Path(sys.argv[3]).read_bytes()
        frame=Path(sys.argv[2]).read_bytes()
        fd=os.memfd_create("inherited-client",os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        os.write(fd,data)
        seals=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,seals)
        sock.sendmsg([frame],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,
                              array.array("i",[fd]))])
        os.close(fd)
        os._exit(0)
    except BaseException:
        os._exit(39)
_,status=os.waitpid(pid,0)
r=json.loads(sock.recv(4096))
sock.close()
print(json.dumps({"result":r,"parent":initiator,"child":pid,"status":status}),flush=True)
"""
        cp=self.unpriv_action(code,self.sock,f,artifact)
        self.assertEqual(cp.returncode,0,cp.stderr)
        data=json.loads(cp.stdout)
        self.assertNotEqual(data["parent"],data["child"])
        self.assertEqual(data["status"],0)
        self.assertFalse(data["result"]["ok"])
        self.assertIsNone(self.active())

    def test_06_POSITIVE_LIMIT_stolen_unused_signed_ticket_is_bearer_capability(self):
        """P1 unresolved: attacker ordinary UID executes independent client
        using a stolen previously signed frame and its matching sealed bytes.
        It possesses NO private signing key. New OS principal verifies ticket
        correctly but cannot distinguish stolen authorized bearer from user
        intent. This MUST remain production HOLD.
        """
        frame,data,_=self.payload()
        f,artifact=self.make_files(frame,data)
        cp=self.unpriv_action(original.UNPRIV_CLIENT,self.sock,f,artifact)
        self.assertEqual(cp.returncode,0,cp.stderr)
        resp=json.loads(cp.stdout)
        self.assertTrue(resp["ok"],resp)
        self.assertEqual(resp["peer_uid"],UNPRIV)
        self.assertEqual(self.active()["seq"],50)

    def test_07_replayed_stolen_ticket_cannot_activate_second_time(self):
        frame,data,_=self.payload()
        first=self.request(frame,data)
        self.assertTrue(first["ok"],first)
        reply=self.request(frame,data)
        self.assertFalse(reply["ok"])
        self.assertEqual([j["seq"] for j in self.ledger()],[50])

    def test_08_concurrent_same_ticket_two_unpriv_clients_at_most_one_commit(self):
        frame,data,_=self.payload()
        with ThreadPoolExecutor(max_workers=2) as p:
            outcomes=list(p.map(lambda _:self.request(frame,data),range(2)))
        self.assertEqual(sum(bool(o["ok"]) for o in outcomes),1,outcomes)
        self.assertEqual([r["seq"] for r in self.ledger()],[50])
        self.assertEqual(self.active()["seq"],50)

    def test_09_ROOT_owned_hmac_journal_corruption_fails_closed_without_erasure(self):
        frame,data,_=self.payload()
        self.assertTrue(self.request(frame,data)["ok"])
        self.stop_server()
        p=self.root/"private"/"journal"/"txn-00000000000000000050.json"
        old=p.read_bytes()
        mutated=old.replace(b'"seq":50',b'"seq":51')
        self.assertNotEqual(old,mutated)
        p.write_bytes(mutated)  # Privileged test fault injection ONLY.
        model=self._root_model()
        with self.assertRaisesRegex(broker.Denied,"unauthenticated"):
            model.recover()
        self.assertEqual(p.read_bytes(),mutated)
        self.assertFalse((self.root/"public"/"not-owned").exists())

    def test_10_foreign_release_collision_preserved_no_signed_activation(self):
        self.stop_server()
        release=self._release_path(50,BLOB)
        release.write_bytes(b"FOREIGN ROOT FIXTURE - DO NOT OVERWRITE")
        old=release.read_bytes()
        self.start_server()
        frame,data,_=self.payload()
        outcome=self.request(frame,data)
        self.assertFalse(outcome["ok"])
        self.assertEqual(release.read_bytes(),old)
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())

    def test_11_actual_unprivileged_write_race_has_no_usable_destination(self):
        frame,data,_=self.payload()
        self.assertTrue(self.request(frame,data)["ok"])
        seq51=self.root/"private"/"journal"/"txn-00000000000000000051.json"
        prior=self.active()
        code="from pathlib import Path;import sys;Path(sys.argv[1]).write_bytes(b'FOREIGN')"
        with ThreadPoolExecutor(max_workers=2) as p:
            futures=[p.submit(self.unpriv_action,code,seq51),
                     p.submit(self.request,*self.payload(
                         seq=51,previous=prior,data=b"REAL-SIGNED-51")[:2])]
            attack=futures[0].result()
            response=futures[1].result()
        self.assertNotEqual(attack.returncode,0)
        self.assertTrue(response["ok"],response)
        self.assertEqual([e["seq"] for e in self.ledger()],[50,51])
        self.assertEqual(prior["seq"],50)

    def test_12_POSITIVE_LIMIT_ticket_not_bound_to_exact_signed_manifest(self):
        """Additional narrower policy ambiguity: valid operation ticket
        for artifact digest+sequence can authorize EITHER of two separately
        valid release-signer approved manifests with differing source commit.
        No release signature is forged. This illustrates a ticket-to-manifest
        binding gap, distinct from ability to steal unused bearer tickets.
        """
        _,data,(manifest,msig,ticket,tsig)=self.payload()
        first=json.loads(manifest.decode("ascii"))
        second=dict(first,source_commit="c"*40)
        secondraw=signed.canonical_bytes(second)
        secondsig=self.release_key.sign(signed.DOMAIN+secondraw)
        self.assertNotEqual(manifest,secondraw)
        self.assertNotEqual(msig,secondsig)
        frame=broker.canonical({
            "metadata":base64.b64encode(secondraw).decode(),
            "release_sig":base64.b64encode(secondsig).decode(),
            "ticket":base64.b64encode(ticket).decode(),
            "ticket_sig":base64.b64encode(tsig).decode()
        })
        answer=self.request(frame,data)
        self.assertTrue(answer["ok"],answer)
        entry=self.ledger()[0]
        self.assertEqual(entry["manifest_hash"],hashlib.sha256(secondraw).hexdigest())
        self.assertNotEqual(entry["manifest_hash"],hashlib.sha256(manifest).hexdigest())
        self.assertEqual(entry["ticket_hash"],hashlib.sha256(ticket).hexdigest())

    def test_13_POSITIVE_LIMIT_orphaned_release_blocks_approved_retry_after_crash(self):
        """Production recovery gap: root broker preserves after_release
        orphan, but O_EXCL blocks reattempt with the very SAME valid ticket
        and artifact. No destructive cleanup is allowed. Requires trusted
        recovery protocol / ownership ledger, not manual 'rm' in production.
        """
        self.stop_server()
        frame,data,(manifest,sig,ticket,ticket_sig)=self.payload()
        fd=os.memfd_create("agent06-real-uid-orphan",os.MFD_ALLOW_SEALING)
        try:
            os.write(fd,BLOB)
            fcntl.fcntl(fd,fcntl.F_ADD_SEALS,broker.REQUIRED_SEALS)
            model=self._root_model()
            with self.assertRaises(broker.Cut):
                model.activate(fd,manifest,sig,ticket,ticket_sig,
                               now=NOW,cut="after_release")
        finally:
            os.close(fd)
        self.assertTrue(self._release_path(50,BLOB).exists())
        self.assertEqual(self.ledger(),[])
        self.start_server()
        retry=self.request(frame,data)  # EXACT same issued ticket+signed manifest
        self.assertFalse(retry["ok"])
        self.assertEqual(self.ledger(),[])
        self.assertIsNone(self.active())
        self.assertEqual(self._release_path(50,BLOB).read_bytes(),BLOB)

    def test_14_root_only_unsigned_activation_and_symlink_fail_closed(self):
        self.stop_server()
        active=self.root/"private"/"active"/"active.json"
        foreign=self.root/"public"/"dont-delete-recording.wav"
        foreign.write_bytes(b"RECORDING-PRESERVE")
        active.symlink_to(foreign)
        model=self._root_model()
        with self.assertRaises(OSError):
            model.recover()
        self.assertEqual(foreign.read_bytes(),b"RECORDING-PRESERVE")
        self.assertTrue(active.is_symlink())

    def test_15_operation_nonce_and_digest_validity_checked_by_trusted_broker(self):
        frame,data,(manifest,msig,ticket,tsig)=self.payload()
        value=json.loads(ticket.decode())
        value["digest"]="0"*64
        forged=broker.canonical(value)
        # Signature of original ticket is NOT valid for altered digest.
        altered=broker.canonical({
            "metadata":base64.b64encode(manifest).decode(),
            "release_sig":base64.b64encode(msig).decode(),
            "ticket":base64.b64encode(forged).decode(),
            "ticket_sig":base64.b64encode(tsig).decode()
        })
        response=self.request(altered,data)
        self.assertFalse(response["ok"])
        self.assertEqual(self.ledger(),[])


if __name__=="__main__":
    unittest.main(verbosity=2)
