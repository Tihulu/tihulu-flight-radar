#!/usr/bin/env python3
"""Disposable CI Ed25519 and sealed-FD adversarial acceptance tests.

Every private signing key is generated only in RAM during the test. The test
public key is pinned by the verifier caller, NOT sourced from the package.
No real keys, installer, download, pipx, sudoers, services or SDR operations.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import flight_signed_installer_ci_prototype as gate

NOW = 1800000000
VALID = b"EPHEMERAL-FLIGHT-CI-PACKAGE-VALID"


@unittest.skipUnless(os.name == "posix", "Linux-only sealed-FD test")
class SignedFixtureCI(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("GITHUB_ACTIONS") != "true" or
                os.environ.get("CI") != "true" or
                not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Dedicated GitHub CI environment required")
        self.tmp = tempfile.TemporaryDirectory(
            prefix="flight-signed-ci-", dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "fixture.bin"
        self.file.write_bytes(VALID)
        self.file.chmod(0o600)
        # Never write, print, log or serialize this ephemeral private key.
        self.signer = Ed25519PrivateKey.generate()
        self.pub = self.signer.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.roots = {"fixture-root": self.pub}
        self.metadata = {
            "schema": 1,
            "app_id": gate.APP_ID,
            "channel": gate.CHANNEL,
            "platform": "linux",
            "architecture": "x86_64",
            "artifact_name": "fixture.bin",
            "artifact_size": len(VALID),
            "artifact_sha256": hashlib.sha256(VALID).hexdigest(),
            "sequence": 8,
            "issued_at": NOW - 3600,
            "expires_at": NOW + 3600,
            "source_commit": "a" * 40,
            "key_id": "fixture-root",
        }

    def envelope(self, *, signer=None, metadata=None):
        payload = gate.canonical_bytes(
            self.metadata if metadata is None else metadata)
        key = self.signer if signer is None else signer
        return payload, key.sign(gate.DOMAIN + payload)

    def verify(self, *, raw=None, signature=None, roots=None, file=None,
               platform="linux", arch="x86_64", minimum=7, now=NOW):
        if raw is None or signature is None:
            raw, signature = self.envelope()
        return gate.verify_and_seal(
            self.file if file is None else file, raw, signature,
            self.roots if roots is None else roots,
            expected_platform=platform, expected_arch=arch,
            minimum_sequence=minimum, now=now)

    def test_01_valid_signature_and_sealed_fd_handoff(self):
        with self.verify() as artifact:
            self.assertEqual(artifact.read(), VALID)
            self.assertEqual(artifact.metadata["sequence"], 8)
            required = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                        fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
            self.assertEqual(fcntl.fcntl(artifact.fd, fcntl.F_GET_SEALS)
                             & required, required)
            with self.assertRaises(OSError):
                os.pwrite(artifact.fd, b"ATTACK", 0)
            fd = artifact.fd
        with self.assertRaises(OSError):
            os.fstat(fd)
        with self.assertRaises(gate.TrustRejected):
            artifact.read()

    def test_02_source_modified_before_copy_is_rejected(self):
        self.file.write_bytes(b"FORGED-EQUAL-LENGTH-ARTIFACT")
        with self.assertRaises(gate.TrustRejected):
            self.verify()

    def test_03_rename_swap_after_open_does_not_change_handoff(self):
        # Deterministic pathname swap AFTER the source FD is opened.
        # The handoff must be sourced from the pinned old FD, not filename.
        real_open = gate._open_source_once
        calls = []
        def attack(path, runner):
            fd = real_open(path, runner)
            calls.append(True)
            self.file.rename(self.root / "old-verified-source")
            self.file.write_bytes(b"AFTER_OPEN_REPLACEMENT")
            return fd
        with patch.object(gate, "_open_source_once", new=attack):
            with self.verify() as artifact:
                self.assertEqual(artifact.read(), VALID)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.file.read_bytes(), b"AFTER_OPEN_REPLACEMENT")
        self.assertEqual((self.root / "old-verified-source").read_bytes(), VALID)

    def test_04_inplace_same_inode_mutation_after_open_fails_closed(self):
        real_open = gate._open_source_once
        calls = []
        def attack(path, runner):
            fd = real_open(path, runner)
            calls.append(True)
            self.file.write_bytes(b"MUTATED-SOURCE-SAME-INODE")
            return fd
        with patch.object(gate, "_open_source_once", new=attack):
            with self.assertRaises(gate.TrustRejected):
                self.verify()
        self.assertEqual(len(calls), 1)

    def test_05_signature_one_byte_forgery_is_rejected(self):
        raw, sig = self.envelope()
        forged = sig[:-1] + bytes([sig[-1] ^ 1])
        with self.assertRaisesRegex(gate.TrustRejected, "signature"):
            self.verify(raw=raw, signature=forged)

    def test_06_attacker_generated_signature_is_rejected(self):
        rogue = Ed25519PrivateKey.generate()
        raw, fake_signature = self.envelope(signer=rogue)
        with self.assertRaisesRegex(gate.TrustRejected, "signature"):
            self.verify(raw=raw, signature=fake_signature)

    def test_07_untrusted_public_key_claim_is_rejected(self):
        rogue = Ed25519PrivateKey.generate()
        raw, signature = self.envelope(signer=rogue)
        with self.assertRaisesRegex(gate.TrustRejected, "signature"):
            self.verify(raw=raw, signature=signature)
        # The public key belongs to caller-trusted policy, not metadata.
        with self.assertRaisesRegex(gate.TrustRejected, "Unknown"):
            self.verify(raw=raw, signature=signature, roots={})

    def test_08_correctly_signed_wrong_platform_is_rejected(self):
        altered = {**self.metadata, "platform": "windows"}
        raw, sig = self.envelope(metadata=altered)
        with self.assertRaisesRegex(gate.TrustRejected, "platform"):
            self.verify(raw=raw, signature=sig)

    def test_09_correctly_signed_wrong_architecture_is_rejected(self):
        altered = {**self.metadata, "architecture": "arm64"}
        raw, sig = self.envelope(metadata=altered)
        with self.assertRaisesRegex(gate.TrustRejected, "architecture"):
            self.verify(raw=raw, signature=sig)

    def test_10_trusted_sequence_blocks_signed_rollback(self):
        with self.assertRaisesRegex(gate.TrustRejected, "rollback"):
            self.verify(minimum=9)
        with self.assertRaisesRegex(gate.TrustRejected, "rollback"):
            self.verify(minimum=10)

    def test_11_wrong_signed_app_or_channel_is_rejected(self):
        for k, val in (("app_id", "different-flight-app"),
                       ("channel", "production")):
            with self.subTest(field=k):
                raw, sig = self.envelope(
                    metadata={**self.metadata, k: val})
                with self.assertRaisesRegex(gate.TrustRejected, "Wrong"):
                    self.verify(raw=raw, signature=sig)

    def test_12_expired_and_future_metadata_are_rejected(self):
        with self.assertRaisesRegex(gate.TrustRejected, "Expired"):
            self.verify(now=NOW + 3601)
        with self.assertRaisesRegex(gate.TrustRejected, "Expired"):
            self.verify(now=NOW - 3601)

    def test_13_duplicate_key_and_noncanonical_metadata_rejected(self):
        raw, sig = self.envelope()
        # Duplicate key with a signed blob invalidates canonical metadata.
        duplicate = raw[:-1] + b',"schema":1}'
        with self.assertRaisesRegex(gate.TrustRejected, "Duplicate"):
            self.verify(raw=duplicate, signature=sig)
        spaced = json.dumps(self.metadata, sort_keys=True).encode("ascii")
        with self.assertRaisesRegex(gate.TrustRejected, "canonical"):
            self.verify(raw=spaced, signature=sig)

    def test_14_symlink_and_hardlink_source_are_rejected(self):
        destination = self.root / "real-original"
        self.file.rename(destination)
        self.file.symlink_to(destination)
        with self.assertRaises(OSError):
            self.verify()
        self.file.unlink()
        os.link(destination, self.file)
        with self.assertRaisesRegex(gate.TrustRejected, "Unsafe"):
            self.verify()

    def test_15_wrong_signed_size_or_hash_is_rejected(self):
        for change in ({"artifact_size": len(VALID)+1},
                       {"artifact_sha256": "0" * 64}):
            with self.subTest(change=change):
                raw, sig = self.envelope(metadata={**self.metadata, **change})
                with self.assertRaises(gate.TrustRejected):
                    self.verify(raw=raw, signature=sig)

    def test_16_metadata_tamper_after_signature_is_rejected(self):
        raw, sig = self.envelope()
        changed = raw.replace(b'"sequence":8', b'"sequence":9')
        self.assertNotEqual(changed, raw)
        with self.assertRaisesRegex(gate.TrustRejected, "signature"):
            self.verify(raw=changed, signature=sig)

    def test_17_domain_separation_enforced(self):
        raw, _ = self.envelope()
        sig = self.signer.sign(raw)  # Signature of JSON alone is invalid.
        with self.assertRaisesRegex(gate.TrustRejected, "signature"):
            self.verify(raw=raw, signature=sig)

    def test_18_extra_and_truncated_source_rejected(self):
        self.file.write_bytes(VALID + b"EXTRA")
        with self.assertRaises(gate.TrustRejected):
            self.verify()
        self.file.write_bytes(VALID[:-1])
        with self.assertRaises(gate.TrustRejected):
            self.verify()

    def test_19_external_source_path_is_rejected(self):
        outsider = self.root.parent / "not-in-disposable" / "fixture.bin"
        # Test a sibling path only; never create or modify this path.
        with self.assertRaisesRegex(gate.TrustRejected, "inside disposable"):
            self.verify(file=outsider)

    def test_20_unsigned_self_hash_cannot_replace_signature(self):
        raw, _ = self.envelope()
        fake = bytes.fromhex(self.metadata["artifact_sha256"]) * 2
        with self.assertRaisesRegex(gate.TrustRejected, "signature"):
            self.verify(raw=raw, signature=fake)

    def test_21_untrusted_source_not_reopened_after_handoff(self):
        real_open = gate._open_source_once
        count = []
        def tracking(path, runner):
            count.append(True)
            return real_open(path, runner)
        with patch.object(gate, "_open_source_once", new=tracking):
            with self.verify() as artifact:
                self.file.write_bytes(b"BAD-BYTES-AFTER-VERIFY")
                self.assertEqual(artifact.read(), VALID)
        self.assertEqual(len(count), 1)

    def test_22_no_ci_context_will_fail_closed(self):
        with patch.dict(os.environ, {"CI": "false"}):
            with self.assertRaisesRegex(gate.TrustRejected, "CI-only"):
                self.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
