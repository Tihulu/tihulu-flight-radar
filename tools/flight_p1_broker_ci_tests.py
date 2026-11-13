#!/usr/bin/env python3
"""Agent 08 independent-scope hostile broker tests: disposable CI only.

Green tests include explicit SAME-UID POSITIVE vulnerability witnesses.
A test asserting that a mock broker store can be overwritten by its UID is
proof of remaining P1, NOT an assurance that the product is secure.
"""
from __future__ import annotations

import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import flight_p1_broker_ci_contract as broker
from tools import flight_signed_installer_ci_prototype as signed

NOW = 1800000000
ARTIFACT = b"AGENT08-BROKER-FD-HANDOFF-DISPOSABLE-V1"


@unittest.skipUnless(os.name == "posix", "Linux CI-only test")
class BrokerContractAdversarialTests(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI") != "true"
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or not os.environ.get("RUNNER_TEMP")
                or not hasattr(os, "memfd_create")):
            self.skipTest("disposable GitHub Actions runner only")
        self.tmp = tempfile.TemporaryDirectory(prefix="agent08-broker-",
                                               dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.place = self.parent / "broker-store"
        self.place.mkdir()
        self.signer = Ed25519PrivateKey.generate()
        self.pub = self.signer.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.roots = {"agent08-fixture": self.pub}
        self.store = broker.DisposableBrokerStore(self.place)
        self.addCleanup(self.store.close)

    def manifest(self, data=ARTIFACT, sequence=50):
        meta = dict(schema=signed.SCHEMA, app_id=signed.APP_ID,
                    channel=signed.CHANNEL, platform="linux",
                    architecture="x86_64", artifact_name="artifact.bin",
                    artifact_size=len(data),
                    artifact_sha256=hashlib.sha256(data).hexdigest(),
                    sequence=sequence, issued_at=NOW - 100,
                    expires_at=NOW + 100, source_commit="a" * 40,
                    key_id="agent08-fixture")
        raw = signed.canonical_bytes(meta)
        return raw, self.signer.sign(signed.DOMAIN + raw)

    def memfd(self, data=ARTIFACT, *, seal=True):
        fd = os.memfd_create("agent08-ci-fd",
                             os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        os.write(fd, data)
        if seal:
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, broker.REQUIRED_SEALS)
        self.addCleanup(os.close, fd)
        return fd

    def install(self, fd, *, sequence=50, data=ARTIFACT, cut=None):
        raw, sig = self.manifest(data, sequence)
        return self.store.install(fd, raw, sig, self.roots, now=NOW, cut=cut)

    def transfer(self, fd):
        s1, s2 = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with s1, s2:
            broker.send_one_fd(s1, fd)
            received, creds = broker.receive_one_fd(s2)
        self.addCleanup(os.close, received)
        return received, creds

    def test_01_prototype_guard_refuses_non_ci_configuration(self):
        saved = os.environ.pop("CI")
        try:
            with self.assertRaises(broker.BrokerRejected):
                broker.ci_only()
        finally:
            os.environ["CI"] = saved

    def test_02_same_uid_peer_credentials_not_privileged_authorization(self):
        fd = self.memfd()
        transferred, creds = self.transfer(fd)
        self.assertGreater(creds[0], 0)
        self.assertEqual(creds[1], os.getuid())
        with self.assertRaisesRegex(broker.BrokerRejected, "same-UID"):
            broker.boundary_assertion(os.getuid(), creds[1])
        self.assertEqual(broker.verify_received_fd(
            transferred, *self.manifest(), self.roots,
            minimum_sequence=50, now=NOW)[1], ARTIFACT)

    def test_03_valid_sealed_fd_single_ipc_transfer_and_install(self):
        transferred, _ = self.transfer(self.memfd())
        release = self.install(transferred)
        self.assertEqual(self.store.pointer()[1],
                         {"seq": 50, "release": release})
        self.assertEqual(self.store.state()[1]["seq"], 50)
        self.assertEqual((self.place / "releases" / release).read_bytes(),
                         ARTIFACT)

    def test_04_hostile_transferred_fd_changed_bytes_rejected(self):
        transferred, _ = self.transfer(self.memfd(b"X" * len(ARTIFACT)))
        with self.assertRaises(broker.BrokerRejected):
            self.install(transferred)
        self.assertIsNone(self.store.pointer()[1])

    def test_05_unsealed_fd_substitution_rejected_even_matching_hash(self):
        transferred, _ = self.transfer(self.memfd(seal=False))
        with self.assertRaises(broker.BrokerRejected):
            self.install(transferred)
        self.assertIsNone(self.store.state()[1])

    def test_06_wrong_length_fd_rejected(self):
        transferred, _ = self.transfer(self.memfd(ARTIFACT + b"!"))
        with self.assertRaises(broker.BrokerRejected):
            self.install(transferred)

    def test_07_forged_manifest_signature_rejected_at_broker(self):
        fd = self.memfd()
        raw, _ = self.manifest()
        imposter = Ed25519PrivateKey.generate()
        wrong_sig = imposter.sign(signed.DOMAIN + raw)
        with self.assertRaises(signed.TrustRejected):
            self.store.install(fd, raw, wrong_sig, self.roots, now=NOW)

    def test_08_self_provided_public_key_is_not_authorized_root(self):
        fd = self.memfd()
        raw, sig = self.manifest()
        evil = Ed25519PrivateKey.generate()
        attacker_policy = {"agent08-fixture": evil.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)}
        with self.assertRaises(signed.TrustRejected):
            self.store.install(fd, raw, sig, attacker_policy, now=NOW)
        # A malicious same-UID caller can alter a Python dict in its OWN
        # interpreter. Real broker roots MUST be external, OS protected.
        self.assertNotEqual(attacker_policy, self.roots)

    def test_09_missing_scm_rights_rejected(self):
        s1, s2 = socket.socketpair()
        with s1, s2:
            s1.sendall(b"F")
            with self.assertRaises(broker.BrokerRejected):
                broker.receive_one_fd(s2)

    def test_10_multiple_fd_substitution_rejected(self):
        a, b = self.memfd(), self.memfd(b"Q" * len(ARTIFACT))
        s1, s2 = socket.socketpair()
        with s1, s2:
            s1.sendmsg([b"F"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                 array.array("i", [a, b]))])
            with self.assertRaises(broker.BrokerRejected):
                broker.receive_one_fd(s2)

    def test_11_identical_distinct_sealed_fd_does_not_break_byte_authority(self):
        fd1 = self.memfd()
        fd2 = self.memfd()
        self.assertNotEqual(os.fstat(fd1).st_ino, os.fstat(fd2).st_ino)
        transferred, _ = self.transfer(fd2)
        self.assertEqual(broker.verify_received_fd(
            transferred, *self.manifest(), self.roots,
            minimum_sequence=50, now=NOW)[1], ARTIFACT)
        # Artifact *byte identity* matters, not caller's claimed FD number.

    def test_12_replayed_signed_release_denied_by_transaction_state(self):
        fd = self.memfd()
        self.install(fd)
        old = self.store.pointer()[0]
        with self.assertRaises(signed.TrustRejected):
            self.install(fd)
        self.assertEqual(self.store.pointer()[0], old)

    def test_13_broker_flock_contention_refuses_parallel_transaction(self):
        external = os.open(self.place / "locks" / "transaction.lock", os.O_RDWR)
        try:
            fcntl.flock(external, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(broker.BrokerRejected, "concurrent"):
                self.install(self.memfd())
        finally:
            os.close(external)
        self.assertIsNone(self.store.pointer()[1])

    def test_14_foreign_release_is_never_overwritten_or_unlinked(self):
        data = b"FOREIGN FILE: DO NOT MODIFY"
        release = "rel-50-" + hashlib.sha256(ARTIFACT).hexdigest()[:24] + ".bin"
        foreign = self.place / "releases" / release
        foreign.write_bytes(data)
        with self.assertRaises(FileExistsError):
            self.install(self.memfd())
        self.assertEqual(foreign.read_bytes(), data)
        self.assertIsNone(self.store.pointer()[1])

    def test_15_foreign_activation_symlink_not_followed_or_removed(self):
        recording = self.parent / "foreign-recording.wav"
        recording.write_bytes(b"RECORDING-PRESERVE")
        (self.place / "activation" / "active.json").symlink_to(recording)
        with self.assertRaises(OSError):
            self.install(self.memfd())
        self.assertEqual(recording.read_bytes(), b"RECORDING-PRESERVE")
        self.assertTrue((self.place / "activation" / "active.json").is_symlink())

    def test_16_reject_intermediate_ancestor_symlink(self):
        fake = self.parent / "alias"
        fake.symlink_to(self.place, target_is_directory=True)
        with self.assertRaises(OSError):
            broker.pinned_root(fake)

    def test_17_namespace_swap_existing_fd_survives_but_PUBLIC_ALIAS_UNSAFE(self):
        # This is a POSITIVE gap witness: same-UID can rename the CI store.
        moved = self.parent / "moved-store"
        os.rename(self.place, moved)
        self.place.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(OSError):
            broker.pinned_root(self.place)
        # The old dirfd is pinned, yet the public original alias is now a
        # symlink the SAME UID could redirect. OS ownership is still missing.
        self.assertEqual(self.install(self.memfd()).startswith("rel-"), True)
        self.assertEqual(self.store.pointer()[1]["seq"], 50)
        self.assertTrue((moved / "activation" / "active.json").exists())

    def test_18_crash_after_release_keeps_old_activation_and_orphan(self):
        foreign = self.parent / "legacy-v031.dat"
        foreign.write_bytes(b"LEGACY")
        with self.assertRaises(broker.SimulatedCrash):
            self.install(self.memfd(), cut="after_release")
        self.assertIsNone(self.store.state()[1])
        self.assertIsNone(self.store.pointer()[1])
        self.assertEqual(len(list((self.place / "releases").glob("rel-*"))), 1)
        self.assertFalse(self.store.recover())
        self.assertEqual(foreign.read_bytes(), b"LEGACY")

    def test_19_crash_after_committed_journal_recovers_atomically(self):
        with self.assertRaises(broker.SimulatedCrash):
            self.install(self.memfd(), cut="after_journal")
        self.assertIsNone(self.store.pointer()[1])
        self.assertTrue(self.store.recover())
        self.assertEqual(self.store.pointer()[1]["seq"], 50)

    def test_20_recovery_refuses_forged_foreign_pointer(self):
        with self.assertRaises(broker.SimulatedCrash):
            self.install(self.memfd(), cut="after_journal")
        raw = b'{"seq":0,"release":"foreign"}'
        foreign = self.place / "activation" / "active.json"
        foreign.write_bytes(raw)
        with self.assertRaises(broker.BrokerRejected):
            self.store.recover()
        self.assertEqual(foreign.read_bytes(), raw)

    def test_21_corrupt_journal_blocks_and_preserves_foreign_files(self):
        state = self.place / "journal" / "current.json"
        state.write_text("not JSON", encoding="ascii")
        original = state.read_bytes()
        with self.assertRaises(broker.BrokerRejected):
            self.install(self.memfd())
        self.assertEqual(state.read_bytes(), original)

    def test_22_unapproved_rollback_is_never_executed(self):
        with self.assertRaises(broker.BrokerRejected):
            self.store.rollback("rel-1", "approve-me")

    def test_23_settings_recordings_and_borrowed_services_untouched(self):
        settings = self.parent / "QSettings-user-backup"
        recording = self.parent / "rtl-recording.iq"
        shared = self.parent / "borrowed-readsb.pid"
        for p, data in ((settings, b"preferences"),
                        (recording, b"IQ" * 20), (shared, b"not-ours")):
            p.write_bytes(data)
        self.install(self.memfd())
        self.assertEqual(settings.read_bytes(), b"preferences")
        self.assertEqual(recording.read_bytes(), b"IQ" * 20)
        self.assertEqual(shared.read_bytes(), b"not-ours")
        self.assertFalse(broker.DEFAULT_BACKGROUND)

    def test_24_same_uid_can_modify_simulated_broker_journal_P1_WITNESS(self):
        self.install(self.memfd())
        target = self.place / "journal" / "current.json"
        prior = target.read_bytes()
        attacker = b'{"seq":0,"release":"evil","digest":"' + b"0" * 64 + b'","previous":null}'
        # A separate ordinary process with this same UID has precisely this
        # access in a user-owned directory; chmod(0700) does not prevent it.
        target.write_bytes(attacker)
        self.assertNotEqual(target.read_bytes(), prior)
        with self.assertRaises(broker.BrokerRejected):
            self.store.recover()
        # This test is deliberately GREEN ON A FAILED SECURITY BOUNDARY.
        # Hence P1 SAME-UID MUST remain HOLD even if all CI tests pass.

    def test_25_recovery_rejects_tampered_committed_release(self):
        self.install(self.memfd())
        rel = self.store.state()[1]["release"]
        (self.place / "releases" / rel).write_bytes(b"tampered!")
        with self.assertRaises(broker.BrokerRejected):
            self.store.recover()

    def test_26_nofollow_rejects_journal_symlink_to_foreign_data(self):
        target = self.parent / "not-ours"
        target.write_bytes(b"KEEP")
        (self.place / "journal" / "current.json").symlink_to(target)
        with self.assertRaises(OSError):
            self.store.recover()
        self.assertEqual(target.read_bytes(), b"KEEP")

    def test_27_version_upgrade_preserves_old_release_and_state(self):
        old = self.install(self.memfd(), sequence=50)
        new_data = b"VERSION-51-DISPOSABLE"
        second = self.memfd(new_data)
        new = self.install(second, sequence=51, data=new_data)
        self.assertNotEqual(old, new)
        self.assertEqual((self.place / "releases" / old).read_bytes(), ARTIFACT)
        self.assertEqual((self.place / "releases" / new).read_bytes(), new_data)
        self.assertEqual(self.store.pointer()[1]["seq"], 51)

    def test_28_sameuid_cannot_be_validated_with_python_mode_bits(self):
        # 0700 looks private, but this same UID still owns/chmods the parent.
        self.assertEqual(os.stat(self.place).st_uid, os.getuid())
        os.chmod(self.place, 0o700)
        self.assertTrue(os.access(self.place, os.W_OK))
        with self.assertRaises(broker.BrokerRejected):
            broker.boundary_assertion(os.getuid(), os.getuid())


if __name__ == "__main__":
    unittest.main(verbosity=2)
