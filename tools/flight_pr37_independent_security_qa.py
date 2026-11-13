#!/usr/bin/env python3
"""Agent 06: independent PR37 signed-byte trust and sealed-memfd red-team QA.

Runs ONLY in a newly-created disposable GitHub Linux RUNNER_TEMP fixture.
Ephemeral test signing keys stay in memory. The tests intentionally include
POSITIVE demonstrations of residual production trust gaps: their PASS
is not security approval. The prior metadata-interface P2 reproducer is now a
NEGATIVE acceptance assertion in the separate remediation branch. No installer, service or owner-machine operations.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import flight_signed_installer_ci_prototype as gate

NOW = 1800000000
CLEAN = b"independent-QA-trusted-artifact-2026"
WRONG = b"FOREIGN-CHANGED-ARTIFACT-2026"


@unittest.skipUnless(os.name == "posix", "Linux-only sealed memfd")
class PR37IndependentSignedQA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("CI") != "true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Only GitHub Actions disposable fixture is allowed")
        self.tmp = tempfile.TemporaryDirectory(
            prefix="flight-agent06-pr37-", dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "input"
        self.folder.mkdir(mode=0o700)
        self.file = self.folder / "package.bin"
        self.file.write_bytes(CLEAN)
        self.file.chmod(0o600)
        self.signer = Ed25519PrivateKey.generate()  # memory ONLY
        self.key = self.signer.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.roots = {"lab-key": self.key}
        self.fields = dict(
            schema=1, app_id=gate.APP_ID, channel=gate.CHANNEL,
            platform="linux", architecture="x86_64",
            artifact_name="package.bin", artifact_size=len(CLEAN),
            artifact_sha256=hashlib.sha256(CLEAN).hexdigest(), sequence=22,
            issued_at=NOW-900, expires_at=NOW+900,
            source_commit="c"*40, key_id="lab-key")

    def envelope(self, fields=None, signer=None):
        raw = gate.canonical_bytes(self.fields if fields is None else fields)
        return raw, (self.signer if signer is None else signer).sign(gate.DOMAIN+raw)

    def accept(self, *, path=None, raw=None, sig=None, roots=None,
               platform="linux", arch="x86_64", minimum=21, now=NOW):
        if raw is None or sig is None:
            raw, sig = self.envelope()
        return gate.verify_and_seal(
            self.file if path is None else path, raw, sig,
            self.roots if roots is None else roots,
            expected_platform=platform, expected_arch=arch,
            minimum_sequence=minimum, now=now)

    def assert_rejected(self, *, regex=None, **kwargs):
        with self.assertRaises(gate.TrustRejected) as ctx:
            with self.accept(**kwargs):
                self.fail("Malicious fixture unexpectedly accepted")
        if regex:
            self.assertIn(regex, str(ctx.exception))

    def test_01_true_ed25519_and_all_linux_memfd_seals(self):
        with self.accept() as data:
            self.assertEqual(data.read(), CLEAN)
            self.assertEqual(data.metadata["artifact_sha256"],
                             hashlib.sha256(CLEAN).hexdigest())
            seals = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                     fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
            self.assertEqual(fcntl.fcntl(data.fd, fcntl.F_GET_SEALS) & seals, seals)
            with self.assertRaises(OSError):
                os.pwrite(data.fd, b"tamper", 0)
            with self.assertRaises(OSError):
                os.ftruncate(data.fd, 0)
            with self.assertRaises((OSError, ValueError)):
                mmap.mmap(data.fd, len(CLEAN), access=mmap.ACCESS_WRITE)
            self.assertEqual(os.pread(data.fd, len(CLEAN), 0), CLEAN)
            fd = data.fd
        with self.assertRaises(OSError):
            os.fstat(fd)
        with self.assertRaises(gate.TrustRejected):
            data.read()

    def test_02_independent_foreign_key_and_signature_forgery(self):
        raw, sig = self.envelope()
        self.assert_rejected(raw=raw, sig=sig[:-1]+bytes([sig[-1]^1]),
                             regex="signature")
        rival = Ed25519PrivateKey.generate()
        raw, rogue_sig = self.envelope(signer=rival)
        self.assert_rejected(raw=raw, sig=rogue_sig, regex="signature")
        self.assert_rejected(raw=raw, sig=rogue_sig, roots={}, regex="Unknown")

    def test_03_domain_separation_and_metadata_post_signature_mutation(self):
        raw, sig = self.envelope()
        self.assert_rejected(raw=raw, sig=self.signer.sign(raw), regex="signature")
        altered = raw.replace(b'"sequence":22', b'"sequence":23')
        self.assertNotEqual(raw, altered)
        self.assert_rejected(raw=altered, sig=sig, regex="signature")

    def test_04_duplicate_and_noncanonical_validly_signed_rejected(self):
        raw, _ = self.envelope()
        duplicate = raw[:-1] + b',"schema":1}'
        dup_sig = self.signer.sign(gate.DOMAIN+duplicate)
        self.assert_rejected(raw=duplicate, sig=dup_sig, regex="Duplicate")
        formatted = json.dumps(self.fields, sort_keys=True).encode("ascii")
        fmt_sig = self.signer.sign(gate.DOMAIN+formatted)
        self.assert_rejected(raw=formatted, sig=fmt_sig, regex="canonical")
        unknown = {**self.fields, "unexpected_capability": True}
        raw2, sig2 = self.envelope(fields=unknown)
        self.assert_rejected(raw=raw2, sig=sig2, regex="Unexpected")

    def test_05_strict_signed_types_and_limits(self):
        for changes in ({"schema": True},
                        {"artifact_size": True},
                        {"issued_at": False},
                        {"sequence": "22"},
                        {"artifact_sha256": "X"*64},
                        {"source_commit": "!"*40},
                        {"artifact_name": "../escape"},
                        {"artifact_name": "."},
                        {"artifact_size": gate.MAX_ARTIFACT+1}):
            with self.subTest(changes=changes):
                raw, sig = self.envelope(fields={**self.fields, **changes})
                self.assert_rejected(raw=raw, sig=sig)
        raw, sig = self.envelope()
        oversized = raw+b" "*(gate.MAX_META+1)
        self.assert_rejected(raw=oversized, sig=sig, regex="length")

    def test_06_correctly_signed_wrong_app_channel_platform_arch(self):
        for k,v in (("app_id","foreign-app"),("channel","stable"),
                    ("platform","windows"),("architecture","aarch64")):
            with self.subTest(field=k):
                raw,sig=self.envelope(fields={**self.fields,k:v})
                self.assert_rejected(raw=raw,sig=sig,regex="Wrong")

    def test_07_expired_future_and_signed_rollback_refused_by_floor(self):
        self.assert_rejected(now=NOW+901,regex="Expired")
        self.assert_rejected(now=NOW-901,regex="Expired")
        self.assert_rejected(minimum=23,regex="rollback")
        with self.accept(minimum=22) as artifact:
            self.assertEqual(artifact.read(),CLEAN)
        # A same-sequence replay is still accepted if a trusted caller does
        # not advance the floor. No durable monotonic state is implemented.
        with self.accept(minimum=22) as replay:
            self.assertEqual(replay.read(),CLEAN)

    def test_08_external_caller_key_origin_is_a_trust_boundary_not_crypto(self):
        attacker = Ed25519PrivateKey.generate()
        attacker_public = attacker.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        raw, rogue_sig = self.envelope(signer=attacker)
        self.assert_rejected(raw=raw,sig=rogue_sig,regex="signature")
        # POSITIVE THREAT-MODEL REPRODUCTION: if a hostile same-UID principal
        # supplies/controls the caller-trusted public key, the same payload
        # with the attacker's signature validates. Not a crypto vulnerability.
        with self.accept(raw=raw,sig=rogue_sig,roots={"lab-key":attacker_public}) as x:
            self.assertEqual(x.read(),CLEAN)

    def test_09_single_open_name_swap_cannot_change_sealed_payload(self):
        real_open=gate._open_source_once
        opens=[]
        saved=self.folder/"saved-original"
        def attack(path,runner):
            fd=real_open(path,runner)
            opens.append(True)
            self.file.rename(saved)
            self.file.write_bytes(WRONG)
            return fd
        with patch.object(gate,"_open_source_once",new=attack):
            with self.accept() as artifact:
                self.assertEqual(artifact.read(),CLEAN)
        self.assertEqual(len(opens),1)
        self.assertEqual(self.file.read_bytes(),WRONG)
        self.assertEqual(saved.read_bytes(),CLEAN)

    def test_10_single_inode_tamper_after_open_rejected(self):
        real_open=gate._open_source_once
        called=[]
        def attack(path,runner):
            fd=real_open(path,runner)
            called.append(True)
            self.file.write_bytes(WRONG)
            return fd
        with patch.object(gate,"_open_source_once",new=attack):
            self.assert_rejected()
        self.assertEqual(len(called),1)

    def test_11_mutation_during_fd_to_memfd_copy_fails_closed(self):
        real_write=gate._write_all
        called=[]
        def attack(fd, bytes_to_copy):
            real_write(fd,bytes_to_copy)
            if not called:
                called.append(True)
                self.file.write_bytes(WRONG)
        with patch.object(gate,"_write_all",new=attack):
            self.assert_rejected()
        self.assertEqual(len(called),1)

    def test_12_staged_memfd_modified_before_sealing_fails_digest(self):
        old_fcntl=fcntl.fcntl
        called=[]
        def attack(fd, cmd, *args):
            if cmd==fcntl.F_ADD_SEALS and not called:
                called.append(True)
                os.pwrite(fd,b"Z",0)
            return old_fcntl(fd,cmd,*args)
        with patch.object(gate.fcntl,"fcntl",new=attack):
            self.assert_rejected(regex="Copied sealed artifact")
        self.assertEqual(len(called),1)

    def test_13_post_return_path_rewrite_does_not_modify_sealed_fd(self):
        with self.accept() as artifact:
            self.file.write_bytes(WRONG)
            self.assertEqual(artifact.read(),CLEAN)
            fd2=os.dup(artifact.fd)
            try:
                self.assertEqual(os.pread(fd2,len(CLEAN),0),CLEAN)
                with self.assertRaises(OSError):
                    os.pwrite(fd2,b"X",0)
            finally:
                os.close(fd2)

    def test_14_source_symlink_hardlink_and_symlink_parent_blocked(self):
        saved=self.folder/"original-file"
        self.file.rename(saved)
        self.file.symlink_to(saved)
        with self.assertRaises(OSError):
            with self.accept():
                self.fail("symlink accepted")
        self.file.unlink()
        os.link(saved,self.file)
        self.assert_rejected(regex="Unsafe")
        self.file.unlink()
        saved.rename(self.file)
        real_dir=self.root/"safe-original-parent"
        self.folder.rename(real_dir)
        self.folder.symlink_to(real_dir,target_is_directory=True)
        with self.assertRaises(OSError):
            with self.accept():
                self.fail("symlink parent accepted")

    def test_15_signed_length_digest_and_trailing_bytes_denied(self):
        self.file.write_bytes(CLEAN+b"TRAIL")
        self.assert_rejected()
        self.file.write_bytes(CLEAN[:-1])
        self.assert_rejected()
        self.file.write_bytes(CLEAN)
        for delta in ({"artifact_size":len(CLEAN)+1},
                      {"artifact_sha256":"0"*64}):
            with self.subTest(delta=delta):
                raw,sig=self.envelope(fields={**self.fields,**delta})
                self.assert_rejected(raw=raw,sig=sig)

    def test_16_outside_runner_or_mismatched_signed_filename_blocked(self):
        external=Path(os.environ["RUNNER_TEMP"]).parent/"outside-runner"/"package.bin"
        self.assert_rejected(path=external,regex="inside disposable")
        other={**self.fields,"artifact_name":"other.bin"}
        raw,sig=self.envelope(fields=other)
        self.assert_rejected(raw=raw,sig=sig,regex="filename")
        # Even a directory symlink to an otherwise allowed target is rejected.
        self.assertEqual(self.file.name, self.fields["artifact_name"])

    def test_17_ci_environment_is_not_the_trusted_os_boundary(self):
        with patch.dict(os.environ,{"CI":"false"}):
            self.assert_rejected(regex="CI-only")
        # A mutable caller policy is not a persisted anti-replay authority.
        # Legitimately signed sequence 22 with minimum=0 still validates.
        with self.accept(minimum=0) as artifact:
            self.assertEqual(artifact.metadata["sequence"],22)

    def test_18_verified_metadata_is_frozen_and_read_length_pinned(self):
        # Previously a POSITIVE P2 vulnerability reproduction. In this
        # new stacked remediation branch only, PASS is NEGATIVE acceptance:
        # consumers cannot change the signed metadata or read byte count.
        from dataclasses import FrozenInstanceError
        with self.accept() as artifact:
            meta = artifact.metadata
            self.assertIsInstance(meta, gate.VerifiedMetadata)
            self.assertNotIsInstance(meta, dict)
            self.assertEqual(artifact.read(), CLEAN)
            with self.assertRaises(TypeError):
                meta["platform"] = "windows"
            with self.assertRaises(TypeError):
                meta["artifact_size"] = 1
            with self.assertRaises(FrozenInstanceError):
                meta.platform = "windows"
            with self.assertRaises(FrozenInstanceError):
                meta.sequence = 0
            with self.assertRaises(FrozenInstanceError):
                artifact.metadata = {"platform": "windows"}
            with self.assertRaises(FrozenInstanceError):
                artifact._verified_length = 1
            copy = artifact.metadata_copy()
            copy["platform"] = "windows"
            copy["architecture"] = "arm64"
            copy["sequence"] = 0
            copy["artifact_size"] = 1
            copy["nested"] = {"version": [1, 2, 3]}
            copy["nested"]["version"].append(4)
            self.assertEqual(artifact.metadata["platform"], "linux")
            self.assertEqual(artifact.metadata["architecture"], "x86_64")
            self.assertEqual(artifact.metadata["sequence"], 22)
            self.assertEqual(artifact.metadata["artifact_size"], len(CLEAN))
            self.assertNotIn("nested", artifact.metadata)
            self.assertEqual(artifact.verified_length, len(CLEAN))
            self.assertEqual(artifact.read(), CLEAN)
            self.assertEqual(os.pread(artifact.fd, len(CLEAN), 0), CLEAN)

    def test_18b_signed_nested_metadata_is_denied(self):
        # The signature may be valid, but arbitrary mutable nested objects
        # must never become an authorised policy snapshot.
        for change in (
            {"platform": {"nested": ["linux"]}},
            {"artifact_size": [len(CLEAN)]},
            {"architecture": {"nested": "x86_64"}},
            {"extensions": {"mutable": ["injected"]}},
        ):
            with self.subTest(change=change):
                raw, sig = self.envelope(fields={**self.fields, **change})
                self.assert_rejected(raw=raw, sig=sig)

    def test_18c_signed_policy_copy_is_independent_of_caller_inputs(self):
        caller_data = dict(self.fields)
        raw, sig = self.envelope(fields=caller_data)
        with self.accept(raw=raw, sig=sig) as artifact:
            caller_data["platform"] = "windows"
            caller_data["sequence"] = 0
            caller_data["artifact_size"] = 1
            caller_data["nested"] = {"permissions": ["all"]}
            self.assertEqual(artifact.metadata["platform"], "linux")
            self.assertEqual(artifact.metadata["sequence"], 22)
            self.assertEqual(artifact.verified_length, len(CLEAN))
            self.assertEqual(artifact.read(), CLEAN)


    def test_19_trusted_time_is_caller_policy_not_clock_bootstrap(self):
        # A signed envelope expired at NOW+900; a caller that supplies an
        # earlier forged "now" accepts it. No trusted clock is implemented.
        self.assert_rejected(now=NOW+901,regex="Expired")
        with self.accept(now=NOW) as replayed:
            self.assertEqual(replayed.read(),CLEAN)

    def test_20_source_commit_is_signed_label_not_attestation(self):
        # Validly signed metadata naming an arbitrary 40-hex commit has not
        # been checked against any reproducible source/build inventory.
        forged_identity={**self.fields,"source_commit":"f"*40}
        raw,sig=self.envelope(fields=forged_identity)
        with self.accept(raw=raw,sig=sig) as artifact:
            self.assertEqual(artifact.metadata["source_commit"],"f"*40)
            self.assertEqual(artifact.read(),CLEAN)


if __name__=="__main__":
    unittest.main(verbosity=2)
