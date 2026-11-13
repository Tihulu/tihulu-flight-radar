#!/usr/bin/env python3
"""Agent 06 — PR47 independent broker/same-UID QA (disposable Linux CI only).

POSITIVE_GAP tests intentionally demonstrate a BROKEN same-UID boundary.
A green test proves an insecurity has been reproducibly witnessed, NOT that
the described OS-protected production broker exists or can be installed.

No disk writes outside a per-test RUNNER_TEMP directory, privileged actions,
production signing keys, service changes, physical SDR, or owner-machine access.
"""
from __future__ import annotations

import array
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import flight_p1_broker_ci_contract as gate
from tools import flight_signed_installer_ci_prototype as trust

NOW=1800000000
PAYLOAD=b"INDEPENDENT-PR47-SIGNED-INERT-ARTIFACT-TEST"
SAME_SIZE=b"X"*len(PAYLOAD)


def pub(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


@unittest.skipUnless(os.name=="posix", "Hosted Linux only")
class PR47IndependentBrokerQA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI")!="true" or
            os.environ.get("GITHUB_ACTIONS")!="true" or
            not os.environ.get("RUNNER_TEMP") or
            not hasattr(os,"memfd_create")):
            self.skipTest("Only disposable CI host")
        self.t=tempfile.TemporaryDirectory(
            prefix="flight-pr47-independent-",dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.t.cleanup)
        self.parent=Path(self.t.name)
        self.path=self.parent/"ci-store"
        self.path.mkdir()
        self.signer=Ed25519PrivateKey.generate()
        self.pins={"independent-test":pub(self.signer)}
        self.broker=gate.DisposableBrokerStore(self.path)
        self.addCleanup(self.broker.close)

    def meta(self, content=PAYLOAD, *, sequence=50, signer=None, name="independent-test"):
        key=self.signer if signer is None else signer
        obj={
            "schema":trust.SCHEMA,"app_id":trust.APP_ID,
            "channel":trust.CHANNEL,"platform":"linux",
            "architecture":"x86_64","artifact_name":"fixture.bin",
            "artifact_size":len(content),
            "artifact_sha256":hashlib.sha256(content).hexdigest(),
            "sequence":sequence,"issued_at":NOW-20,
            "expires_at":NOW+20,"source_commit":"a"*40,
            "key_id":name,
        }
        raw=trust.canonical_bytes(obj)
        return raw,key.sign(trust.DOMAIN+raw)

    def mem(self, content=PAYLOAD, *, seal=True):
        fd=os.memfd_create("independent-pr47",os.MFD_ALLOW_SEALING|os.MFD_CLOEXEC)
        os.write(fd,content)
        if seal:
            fcntl.fcntl(fd,fcntl.F_ADD_SEALS,gate.REQUIRED_SEALS)
        self.addCleanup(os.close,fd)
        return fd

    def install(self, fd=None, *, content=PAYLOAD, sequence=50, cut=None,
                roots=None, signer=None):
        if fd is None:
            fd=self.mem(content)
        raw,sig=self.meta(content,sequence=sequence,signer=signer)
        return self.broker.install(fd,raw,sig,self.pins if roots is None else roots,
                                   now=NOW,cut=cut)

    def send(self, fd, count=1, payload=b"F"):
        left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            if count:
                rights=array.array("i",[fd]*count)
                left.sendmsg([payload],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,rights)])
            else:
                left.sendall(payload)
            return gate.receive_one_fd(right)
        finally:
            left.close()
            right.close()

    def test_01_legitimate_kernel_fd_handoff_signature_and_digest(self):
        source=self.mem()
        new,creds=self.send(source)
        try:
            self.assertEqual(creds[1],os.getuid())
            self.assertNotEqual(source,new)
            md,actual=gate.verify_received_fd(
                new,*self.meta(),self.pins,minimum_sequence=50,now=NOW)
            self.assertEqual(actual,PAYLOAD)
            self.assertEqual(md.sequence,50)
            self.assertTrue(fcntl.fcntl(new,fcntl.F_GET_SEALS)&gate.REQUIRED_SEALS
                            ==gate.REQUIRED_SEALS)
            self.assertEqual(self.install(new).startswith("rel-50"),True)
        finally:
            os.close(new)

    def test_02_missing_scm_rights_denied(self):
        with self.assertRaisesRegex(gate.BrokerRejected,"missing"):
            self.send(self.mem(),count=0)

    def test_03_two_scm_rights_descriptors_denied_and_sender_fds_preserved(self):
        a=self.mem()
        with self.assertRaisesRegex(gate.BrokerRejected,"multiple"):
            self.send(a,count=2)
        self.assertEqual(os.pread(a,len(PAYLOAD),0),PAYLOAD)

    def test_04_wrong_ipc_frame_denied(self):
        with self.assertRaisesRegex(gate.BrokerRejected,"malformed"):
            self.send(self.mem(),payload=b"Z")

    def test_05_foreign_sealed_bytes_same_length_rejected(self):
        fd=self.mem(SAME_SIZE)
        with self.assertRaises(gate.BrokerRejected):
            self.install(fd)
        self.assertIsNone(self.broker.state()[1])

    def test_06_unsealed_matching_digest_rejected(self):
        with self.assertRaisesRegex(gate.BrokerRejected,"unsealed"):
            self.install(self.mem(seal=False))
        self.assertIsNone(self.broker.state()[1])

    def test_07_wrong_length_even_if_sealed_denied(self):
        with self.assertRaisesRegex(gate.BrokerRejected,"unsealed"):
            self.install(self.mem(PAYLOAD+b"!"))

    def test_08_real_signed_meta_modified_without_resigning_rejected(self):
        raw,sig=self.meta()
        raw=raw.replace(b'"sequence":50',b'"sequence":51')
        with self.assertRaises(trust.TrustRejected):
            self.broker.install(self.mem(),raw,sig,self.pins,now=NOW)

    def test_09_untrusted_signature_from_other_key_rejected(self):
        raw,_=self.meta()
        rogue=Ed25519PrivateKey.generate()
        with self.assertRaises(trust.TrustRejected):
            self.broker.install(
                self.mem(),raw,rogue.sign(trust.DOMAIN+raw),
                self.pins,now=NOW)

    def test_10_nonregular_pipe_fd_rejected_with_no_state_change(self):
        r,w=os.pipe()
        try:
            with self.assertRaises(gate.BrokerRejected):
                self.install(r)
        finally:
            os.close(r)
            os.close(w)
        self.assertIsNone(self.broker.state()[1])

    def test_11_symlink_release_directory_forbidden_to_pinned_walk(self):
        self.broker.close()
        outside=self.parent/"foreign-release-target"
        outside.mkdir()
        os.rmdir(self.path/"releases")
        (self.path/"releases").symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError):
            gate.DisposableBrokerStore(self.path)
        self.assertEqual(list(outside.iterdir()),[])

    def test_12_ancestor_symlink_refused(self):
        link=self.parent/"external-alias"
        link.symlink_to(self.path,target_is_directory=True)
        with self.assertRaises(OSError):
            gate.pinned_root(link)

    def test_13_foreign_named_release_never_overwritten(self):
        name="rel-50-"+hashlib.sha256(PAYLOAD).hexdigest()[:24]+".bin"
        external=self.path/"releases"/name
        data=b"FOREIGN-KEEP-EXACT"
        external.write_bytes(data)
        with self.assertRaises(FileExistsError):
            self.install()
        self.assertEqual(external.read_bytes(),data)
        self.assertIsNone(self.broker.pointer()[1])

    def test_14_symlink_activation_to_foreign_data_not_followed(self):
        outside=self.parent/"not-ours-recording.wav"
        outside.write_bytes(b"RECORDED-IQ-PRESERVE")
        (self.path/"activation"/"active.json").symlink_to(outside)
        with self.assertRaises(OSError):
            self.install()
        self.assertEqual(outside.read_bytes(),b"RECORDED-IQ-PRESERVE")

    def test_15_inprocess_flock_conflict_denies_reentrant_tx(self):
        with self.broker.transaction():
            with self.assertRaisesRegex(gate.BrokerRejected,"already servicing"):
                self.install()
        self.assertIsNone(self.broker.pointer()[1])

    def test_16_external_lock_fd_denies_parallel_tx(self):
        fd=os.open(self.path/"locks"/"transaction.lock",os.O_RDWR)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(gate.BrokerRejected,"concurrent"):
                self.install()
        finally:
            os.close(fd)

    def test_17_crash_before_journal_keeps_orphan_and_foreign_data(self):
        foreign=self.path/"releases"/"user-data.bin"
        foreign.write_bytes(b"KEEP-BYTES")
        with self.assertRaises(gate.SimulatedCrash):
            self.install(cut="after_release")
        self.assertIsNone(self.broker.state()[1])
        self.assertFalse(self.broker.recover())
        self.assertEqual(foreign.read_bytes(),b"KEEP-BYTES")
        self.assertEqual(len(list((self.path/"releases").glob("rel-*.bin"))),1)

    def test_18_crash_after_journal_recovers_only_matching_signed_bytes_fixture(self):
        with self.assertRaises(gate.SimulatedCrash):
            self.install(cut="after_journal")
        self.assertIsNone(self.broker.pointer()[1])
        self.assertTrue(self.broker.recover())
        self.assertEqual(self.broker.pointer()[1]["seq"],50)
        self.assertTrue(self.broker.recover())

    def test_19_foreign_journal_bytes_preserved_on_rejection(self):
        target=self.path/"journal"/"current.json"
        original=b"foreign-invalid-non-json"
        target.write_bytes(original)
        with self.assertRaises(gate.BrokerRejected):
            self.install()
        self.assertEqual(target.read_bytes(),original)

    def test_20_corrupted_recorded_release_denies_recovery(self):
        self.install()
        state=self.broker.state()[1]
        (self.path/"releases"/state["release"]).write_bytes(b"TAMPERED")
        with self.assertRaisesRegex(gate.BrokerRejected,"missing/modified"):
            self.broker.recover()

    def test_21_downgrade_replay_blocked_by_current_simulated_journal(self):
        self.install()
        with self.assertRaises(trust.TrustRejected):
            self.install(sequence=50)
        with self.assertRaises(trust.TrustRejected):
            self.install(sequence=49)
        self.assertEqual(self.broker.state()[1]["seq"],50)

    def test_22_signer_is_not_self_supplied_when_known_pin_is_unchanged(self):
        attacker=Ed25519PrivateKey.generate()
        raw,sig=self.meta(signer=attacker)
        with self.assertRaises(trust.TrustRejected):
            self.broker.install(self.mem(),raw,sig,self.pins,now=NOW)

    def test_23_sameuid_boundary_assertion_refuses_equality(self):
        with self.assertRaisesRegex(gate.BrokerRejected,"same-UID"):
            gate.boundary_assertion(os.getuid(),os.getuid())
        self.assertTrue(gate.boundary_assertion(os.getuid()+1,os.getuid()))

    def test_24_POSITIVE_GAP_user_writable_root_parent_can_move_after_fd_pin(self):
        """Same UID changes public path while existing pinned directory works.
        Green-on-vulnerability. Independent production broker must protect
        ALL ancestors by a separate OS principal, not only use dirfds.
        """
        moved=self.parent/"stolen-public-namespace"
        self.path.rename(moved)
        fake=self.path
        fake.mkdir()
        (fake/"attacker-banner").write_bytes(b"NOT-THE-BROKER")
        release=self.install()
        self.assertTrue((moved/"releases"/release).exists())
        self.assertFalse((fake/"releases").exists())
        self.assertEqual((fake/"attacker-banner").read_bytes(),b"NOT-THE-BROKER")

    def test_25_POSITIVE_GAP_sameuid_can_forge_journal_and_activate_unsigned_blob(self):
        """An external same-UID actor can invent release, journal and digest.
        Recover() validates the hash but no signer/custody of journal.
        This is the CI model, NOT an installed privileged broker flaw.
        """
        data=b"NOT-A-SIGNED-FLIGHT-ARTIFACT"
        name="unsigned-foreign.bin"
        (self.path/"releases"/name).write_bytes(data)
        record={"seq":123456,"release":name,
                "digest":hashlib.sha256(data).hexdigest(),"previous":None}
        (self.path/"journal"/"current.json").write_bytes(
            json.dumps(record,sort_keys=True,separators=(",",":")).encode())
        self.assertTrue(self.broker.recover())
        self.assertEqual(self.broker.pointer()[1],
                         {"seq":123456,"release":name})
        self.assertEqual((self.path/"releases"/name).read_bytes(),data)

    def test_26_POSITIVE_GAP_sameuid_can_substitute_held_journal_before_atomic_replace(self):
        """Independently interpose between equality check and os.replace.
        Signed second update silently overwrites foreign bytes inserted by a
        same-UID adversary in the writable journal namespace. No production
        foreign-byte preservation guarantee can be inferred from green tests.
        """
        self.install()
        target=self.path/"journal"/"current.json"
        attacker=b'{"seq":-1,"release":"FOREIGN-NOT-OURS","digest":"00","previous":null}'
        real=os.replace
        touched=[]
        def inject(src,dst,*a,**kw):
            if src=="current.json.broker-new" and dst=="current.json":
                target.write_bytes(attacker)
                touched.append(True)
            return real(src,dst,*a,**kw)
        newdata=b"VALID-SIGNED-CI-FIXTURE-V51"
        with patch.object(gate.os,"replace",side_effect=inject):
            self.install(content=newdata,sequence=51)
        self.assertEqual(touched,[True])
        self.assertNotEqual(target.read_bytes(),attacker)
        self.assertEqual(self.broker.state()[1]["seq"],51)

    def test_27_POSITIVE_GAP_sameuid_can_replace_configured_verification_roots(self):
        """Passing a different user-owned trust dict causes accepted self-pin.
        This is a P1 missing immutable independently enrolled root, NOT a
        novel cryptographic signing failure.
        """
        rogue=Ed25519PrivateKey.generate()
        rogue_roots={"independent-test":pub(rogue)}
        self.assertNotEqual(rogue_roots,self.pins)
        signed_release=self.install(roots=rogue_roots,signer=rogue)
        self.assertIn("rel-50-",signed_release)

    def test_28_POSITIVE_GAP_0700_directory_still_writable_by_same_uid(self):
        os.chmod(self.path,0o700)
        self.assertEqual(self.path.stat().st_uid,os.getuid())
        self.assertTrue(os.access(self.path,os.W_OK))

    def test_29_POSITIVE_GAP_peercred_from_socketpair_does_not_prove_sender_pid(self):
        """Linux SO_PEERCRED identifies peer credentials at socketpair()
        creation. Another inherited socket holder (child) can send later.
        A same-UID service cannot infer per-request independent user intent.
        """
        source=self.mem()
        left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        right.settimeout(4)
        parent_pid=os.getpid()
        childpid=os.fork()
        if childpid==0:
            try:
                right.close()
                gate.send_one_fd(left,source)
                os._exit(0)
            except BaseException:
                os._exit(37)
        try:
            left.close()
            recv,creds=gate.receive_one_fd(right)
            try:
                self.assertEqual(creds[0],parent_pid)
                self.assertNotEqual(creds[0],childpid)
                self.assertEqual(creds[1],os.getuid())
                self.assertEqual(os.pread(recv,len(PAYLOAD),0),PAYLOAD)
            finally:
                os.close(recv)
        finally:
            right.close()
            _,status=os.waitpid(childpid,0)
            self.assertTrue(os.WIFEXITED(status))
            self.assertEqual(os.WEXITSTATUS(status),0)

    def test_30_foreign_settings_archives_services_never_touched_by_model(self):
        foreign={
            "settings.conf":b"QSettings keep",
            "prior-flight-031.bin":b"LEGACY RELEASE",
            "recording-iq.raw":b"\x00\xfe"*8,
            "borrowed-readsb.pid":b"do not touch",
        }
        for name,data in foreign.items():
            (self.parent/name).write_bytes(data)
        self.install()
        for name,data in foreign.items():
            self.assertEqual((self.parent/name).read_bytes(),data)
        self.assertFalse(gate.DEFAULT_BACKGROUND)

    def test_31_rollback_without_verified_ticket_explicitly_denied(self):
        self.install()
        with self.assertRaisesRegex(gate.BrokerRejected,"not implemented"):
            self.broker.rollback("rel-other","fake approval")

    def test_32_disposable_ci_guard_does_not_prove_production_service(self):
        with patch.dict(os.environ,{"CI":"false"}):
            with self.assertRaises(gate.BrokerRejected):
                gate.ci_only()
        self.assertNotIn("broker authorized",gate.__doc__.lower())


if __name__=="__main__":
    unittest.main(verbosity=2)
