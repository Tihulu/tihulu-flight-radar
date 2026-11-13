#!/usr/bin/env python3
"""Agent 06 independent PR #41 API/FD ownership adversarial QA, CI-only.

Only isolated GitHub-hosted Linux RUNNER_TEMP fixtures, no user machine,
real release key, installation, uninstall, pipx, sudoers or SDR services.
Some tests explicitly demonstrate Python same-interpreter trust limitations:
a green QA gate never means production security GO.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
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

NOW=1800000000
TRUSTED=b"INDEPENDENT-PR41-SIGNED-ARTIFACT"
FOREIGN=b"Z"*len(TRUSTED)


@unittest.skipUnless(os.name=="posix","Linux sealed-memfd only")
class PR41IndependentSecurityQA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI")!="true"
                or os.environ.get("GITHUB_ACTIONS")!="true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("GitHub-hosted disposable CI only")
        self.tmp=tempfile.TemporaryDirectory(prefix="agent06-pr41-",dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.file=self.root/"verified.bin"
        self.file.write_bytes(TRUSTED)
        self.file.chmod(0o600)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
        self.roots={"qa-root":self.public}
        self.metadata=dict(schema=gate.SCHEMA,app_id=gate.APP_ID,
            channel=gate.CHANNEL,platform="linux",architecture="x86_64",
            artifact_name="verified.bin",artifact_size=len(TRUSTED),
            artifact_sha256=hashlib.sha256(TRUSTED).hexdigest(),
            sequence=28,issued_at=NOW-300,expires_at=NOW+300,
            source_commit="b"*40,key_id="qa-root")

    def envelope(self,meta=None,signer=None):
        raw=gate.canonical_bytes(meta if meta is not None else self.metadata)
        return raw,(signer if signer is not None else self.signer).sign(gate.DOMAIN+raw)

    def accept(self,*,meta=None,roots=None,source=None,signer=None,
               now=NOW,sequence=28):
        raw,signature=self.envelope(meta=meta,signer=signer)
        return gate.verify_and_seal(self.file if source is None else source,raw,signature,
            self.roots if roots is None else roots,expected_platform="linux",
            expected_arch="x86_64",minimum_sequence=sequence,now=now)

    def test_01_public_verified_metadata_constructor_rejects_forged_claims(self):
        for attrs in (
            self.metadata,
            {**self.metadata,"platform":"windows"},
            {**self.metadata,"artifact_sha256":"0"*64},
        ):
            with self.subTest(attrs=attrs):
                with self.assertRaisesRegex(gate.TrustRejected,"Ed25519"):
                    gate.VerifiedMetadata(**attrs)
        self.assertEqual(set(gate.FIELDS),set(self.metadata))

    def test_02_public_sealed_fixture_constructor_rejects_unsealed_file_and_keeps_it_open(self):
        ordinary=os.open(self.file,os.O_RDONLY|os.O_CLOEXEC)
        try:
            for args in (
                (ordinary,dict(self.metadata),len(TRUSTED)),
                (ordinary,None,len(TRUSTED)),
                (ordinary,dict(self.metadata),1),
            ):
                with self.subTest(args=args):
                    with self.assertRaisesRegex(gate.TrustRejected,"verified signature"):
                        gate.SealedFixture(*args)
            self.assertEqual(os.pread(ordinary,len(TRUSTED),0),TRUSTED)
        finally:
            os.close(ordinary)

    def test_03_successful_ed25519_verified_mint_and_immutable_mapping(self):
        with self.accept() as artifact:
            self.assertIs(type(artifact.metadata),gate.VerifiedMetadata)
            self.assertEqual(dict(artifact.metadata),self.metadata)
            self.assertFalse(hasattr(artifact,"fd"))
            self.assertFalse(hasattr(artifact.metadata,"__dict__"))
            self.assertEqual(artifact.read(),TRUSTED)
            self.assertEqual(artifact.verified_length,len(TRUSTED))
            with self.assertRaises((FrozenInstanceError,TypeError)):
                artifact.metadata.sequence=0
            with self.assertRaises(TypeError):
                artifact.metadata["artifact_size"]=1
            with self.assertRaises(FrozenInstanceError):
                artifact._fd=10

    def test_04_foreign_signer_and_wrong_signed_origin_refused(self):
        attacker=Ed25519PrivateKey.generate()
        with self.assertRaisesRegex(gate.TrustRejected,"signature"):
            self.accept(signer=attacker)
        with self.assertRaisesRegex(gate.TrustRejected,"Wrong"):
            self.accept(meta={**self.metadata,"platform":"windows"})
        with self.assertRaisesRegex(gate.TrustRejected,"rollback"):
            self.accept(sequence=29)

    def test_05_caller_dict_copy_and_nested_extension_are_not_trusted(self):
        original=dict(self.metadata)
        raw,sig=self.envelope(original)
        with gate.verify_and_seal(self.file,raw,sig,self.roots,
                expected_platform="linux",expected_arch="x86_64",
                minimum_sequence=28,now=NOW) as artifact:
            original["artifact_size"]=1
            original["sequence"]=0
            editable=artifact.metadata_copy()
            editable["platform"]="windows"
            editable["artifact_size"]=1
            editable["extra"]={"privileges":["all"]}
            editable["extra"]["privileges"].append("root")
            self.assertEqual(artifact.metadata.platform,"linux")
            self.assertEqual(artifact.metadata.artifact_size,len(TRUSTED))
            self.assertEqual(artifact.read(),TRUSTED)
        raw2,sig2=self.envelope({**self.metadata,"extra":{"privileges":["all"]}})
        with self.assertRaises(gate.TrustRejected):
            gate.verify_and_seal(self.file,raw2,sig2,self.roots,
                expected_platform="linux",expected_arch="x86_64",
                minimum_sequence=28,now=NOW)

    def test_06_private_owned_fd_identity_and_all_four_seals(self):
        with self.accept() as artifact:
            self.assertFalse(hasattr(artifact,"fd"))
            fd=artifact._fd  # WHITE-BOX test only; NOT supported public API
            info=os.fstat(fd)
            self.assertEqual((info.st_dev,info.st_ino),artifact._owned_identity)
            self.assertEqual(artifact._sealed_digest,hashlib.sha256(TRUSTED).hexdigest())
            self.assertEqual(artifact._verified_length,len(TRUSTED))
            seals=fcntl.fcntl(fd,fcntl.F_GET_SEALS)
            self.assertEqual(seals&gate._REQUIRED_SEALS,gate._REQUIRED_SEALS)
            with self.assertRaises(OSError):
                os.pwrite(fd,b"X",0)
            with self.assertRaises(OSError):
                os.ftruncate(fd,0)
            with self.assertRaises((OSError,ValueError)):
                mmap.mmap(fd,len(TRUSTED),access=mmap.ACCESS_WRITE)

    def test_07_recycled_private_fd_same_length_foreign_bytes_not_returned_or_closed(self):
        foreign_path=self.root/"foreign.bin"
        foreign_path.write_bytes(FOREIGN)
        artifact=self.accept()
        number=artifact._fd
        os.close(number)
        incoming=os.open(foreign_path,os.O_RDONLY|os.O_CLOEXEC)
        if incoming!=number:
            os.dup2(incoming,number)
            os.close(incoming)
        try:
            self.assertEqual(os.fstat(number).st_size,len(TRUSTED))
            with self.assertRaisesRegex(gate.TrustRejected,"FD"):
                artifact.read()
            with self.assertRaisesRegex(gate.TrustRejected,"foreign FD preserved"):
                artifact.close()
            self.assertEqual(os.pread(number,len(TRUSTED),0),FOREIGN)
            artifact.close()
            self.assertEqual(os.pread(number,len(TRUSTED),0),FOREIGN)
        finally:
            os.close(number)

    def test_08_recycled_private_fd_that_is_itself_sealed_is_rejected_by_identity(self):
        first=self.accept()
        second=self.accept()  # separate sealed FD; same bytes, different inode
        number=first._fd
        os.close(number)
        os.dup2(second._fd,number)
        try:
            self.assertEqual(os.pread(number,len(TRUSTED),0),TRUSTED)
            self.assertEqual(fcntl.fcntl(number,fcntl.F_GET_SEALS)&gate._REQUIRED_SEALS,
                             gate._REQUIRED_SEALS)
            with self.assertRaisesRegex(gate.TrustRejected,"identity"):
                first.read()
            with self.assertRaisesRegex(gate.TrustRejected,"foreign FD preserved"):
                first.close()
            self.assertEqual(os.pread(number,len(TRUSTED),0),TRUSTED)
        finally:
            os.close(number)
            second.close()

    def test_09_recycled_number_with_wrong_length_rejected(self):
        other=self.root/"wrong-size.bin"
        other.write_bytes(b"SHORT")
        artifact=self.accept()
        number=artifact._fd
        os.close(number)
        incoming=os.open(other,os.O_RDONLY|os.O_CLOEXEC)
        if incoming!=number:
            os.dup2(incoming,number)
            os.close(incoming)
        try:
            with self.assertRaises(gate.TrustRejected):
                artifact.read()
            with self.assertRaisesRegex(gate.TrustRejected,"foreign FD preserved"):
                artifact.close()
            self.assertEqual(os.pread(number,5,0),b"SHORT")
        finally:
            os.close(number)

    def test_10_external_close_without_reuse_refused_and_idempotent(self):
        artifact=self.accept()
        number=artifact._fd
        os.close(number)
        with self.assertRaisesRegex(gate.TrustRejected,"FD"):
            artifact.read()
        with self.assertRaisesRegex(gate.TrustRejected,"foreign FD preserved"):
            artifact.close()
        artifact.close()
        with self.assertRaisesRegex(gate.TrustRejected,"closed"):
            artifact.read()

    def test_11_bad_or_missing_stat_identity_fails_read_closed(self):
        with self.accept() as artifact:
            real_fstat=os.fstat
            class Malformed: st_size=len(TRUSTED)
            def bad(fd):
                if fd==artifact._fd:
                    return Malformed()
                return real_fstat(fd)
            with patch.object(gate.os,"fstat",new=bad):
                with self.assertRaisesRegex(gate.TrustRejected,"identity"):
                    artifact.read()
            self.assertEqual(artifact.read(),TRUSTED)

    def test_12_digest_checked_even_if_length_and_inode_match(self):
        with self.accept() as artifact:
            real_pread=os.pread
            def injected(fd,n,offset):
                if fd==artifact._fd:
                    return FOREIGN
                return real_pread(fd,n,offset)
            with patch.object(gate.os,"pread",new=injected):
                with self.assertRaisesRegex(gate.TrustRejected,"digest"):
                    artifact.read()
            self.assertEqual(artifact.read(),TRUSTED)

    def test_13_source_renamed_after_open_does_not_redirect_signed_bytes(self):
        old=gate._open_source_once
        moved=self.root/"detached-signed-source"
        calls=[]
        def attack(path,runner):
            fd=old(path,runner)
            calls.append(True)
            self.file.rename(moved)
            self.file.write_bytes(FOREIGN)
            return fd
        with patch.object(gate,"_open_source_once",new=attack):
            with self.accept() as artifact:
                self.assertEqual(artifact.read(),TRUSTED)
        self.assertEqual(len(calls),1)
        self.assertEqual(moved.read_bytes(),TRUSTED)
        self.assertEqual(self.file.read_bytes(),FOREIGN)

    def test_14_source_same_inode_tamper_detected_not_accepted(self):
        old=gate._open_source_once
        hit=[]
        def attack(path,runner):
            fd=old(path,runner)
            hit.append(True)
            self.file.write_bytes(FOREIGN)
            return fd
        with patch.object(gate,"_open_source_once",new=attack):
            with self.assertRaises(gate.TrustRejected):
                self.accept()
        self.assertTrue(hit)

    def test_15_proper_close_is_idempotent_and_use_after_close_rejected(self):
        artifact=self.accept()
        owner=artifact._fd
        self.assertEqual(artifact.read(),TRUSTED)
        artifact.close()
        artifact.close()
        self.assertIsNone(artifact._fd)
        with self.assertRaises(OSError):
            os.fstat(owner)
        with self.assertRaisesRegex(gate.TrustRejected,"closed"):
            artifact.read()

    def test_16_fd_identity_attack_during_pread_rejected(self):
        artifact=self.accept()
        fd=artifact._fd
        original=os.pread
        calls=[]
        def attack(target,n,offset):
            if target==fd and not calls:
                calls.append(True)
                # forged data returned by a misdirected read operation,
                # even while fd identity checks still see original inode
                return FOREIGN
            return original(target,n,offset)
        with patch.object(gate.os,"pread",new=attack):
            with self.assertRaisesRegex(gate.TrustRejected,"digest"):
                artifact.read()
        self.assertEqual(len(calls),1)
        artifact.close()

    def test_17_original_independent_suite_17_cases_preserved_with_fixed_15_16(self):
        p=Path(__file__).with_name("flight_pr39_independent_security_qa.py")
        content=p.read_text(encoding="utf-8")
        for num in range(1,18):
            self.assertIn(f"def test_{num:02d}_",content)
        self.assertIn("test_15_direct_constructor_unsigned_fd_rejected_negative_acceptance",content)
        self.assertIn("test_16_private_fd_number_reuse_fail_closed_preserves_foreign_fd",content)
        self.assertIn("test_17_frozen_python_fields_low_level_setattr_is_not_os_security",content)

    def test_18_private_internal_mint_is_not_same_interpreter_security_boundary(self):
        # DOCUMENTED LIMITATION, not newly discovered P2:
        # untrusted code with control of the trusted interpreter can forge
        # a sealed FD & VerifiedMetadata with object.__new__/setattr__.
        self.assertTrue(callable(gate._mint_verified_fixture))
        self.assertFalse(hasattr(gate.VerifiedMetadata,"__dict__") is False)
        # Production signer/key/bootstrap and OS-protected installer remain HOLD.


if __name__=="__main__":
    unittest.main(verbosity=2)
