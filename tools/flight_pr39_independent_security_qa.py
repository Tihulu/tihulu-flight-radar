#!/usr/bin/env python3
"""Independent Agent 06 exact-HEAD PR39 metadata / FD-lifecycle security QA.

Hosted disposable Linux CI ONLY. Never installs software or accesses the
owner workstation, SDR hardware, pipx, sudoers, or host services.

IMPORTANT: Tests 15, 16, and 17 deliberately PASS when residual prototype
trust/API weaknesses are reproduced. A passing negative/positive test suite
does NOT authorize public release or indicate production security.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
import dataclasses
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import flight_signed_installer_ci_prototype as gate

NOW=1800000000
GOOD=b"INDEPENDENT-PR39-TEST-SEALED-IMAGE-1"


@unittest.skipUnless(os.name=="posix", "Linux-only sealed FD tests")
class IndependentPR39QA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI")!="true"
                or os.environ.get("GITHUB_ACTIONS")!="true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("GitHub-hosted disposable Linux CI only")
        self.tmp=tempfile.TemporaryDirectory(
            prefix="flight-pr39-agent06-",dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.file=self.root/"artifact.bin"
        self.file.write_bytes(GOOD)
        self.file.chmod(0o600)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.roots={"key":self.public}
        self.fields=dict(
            schema=1,app_id=gate.APP_ID,channel=gate.CHANNEL,
            platform="linux",architecture="x86_64",
            artifact_name="artifact.bin",artifact_size=len(GOOD),
            artifact_sha256=hashlib.sha256(GOOD).hexdigest(),
            sequence=23,issued_at=NOW-100,expires_at=NOW+100,
            source_commit="f"*40,key_id="key")

    def envelope(self,fields=None,signer=None):
        data=gate.canonical_bytes(self.fields if fields is None else fields)
        return data,(signer or self.signer).sign(gate.DOMAIN+data)

    def accept(self,raw=None,signature=None,source=None,trust_roots=None,
               minimum=22,now=NOW):
        if raw is None or signature is None:
            raw,signature=self.envelope()
        return gate.verify_and_seal(
            self.file if source is None else source,
            raw,signature,self.roots if trust_roots is None else trust_roots,
            expected_platform="linux",expected_arch="x86_64",
            minimum_sequence=minimum,now=now)

    def test_01_typed_frozen_slotted_mapping_keeps_13_signed_fields(self):
        with self.accept() as f:
            m=f.metadata
            self.assertIs(type(m),gate.VerifiedMetadata)
            self.assertIsInstance(m,Mapping)
            self.assertEqual(set(m),gate.FIELDS)
            self.assertEqual(len(m),13)
            self.assertFalse(hasattr(m,"__dict__"))
            self.assertEqual(m.artifact_size,len(GOOD))
            self.assertEqual(m["artifact_size"],len(GOOD))
            self.assertEqual(f.read(),GOOD)
            self.assertEqual(f.verified_length,len(GOOD))

    def test_02_attribute_mapping_and_unsigned_extension_mutation_rejected(self):
        with self.accept() as f:
            m=f.metadata
            for key,value in (("platform","windows"),("architecture","arm64"),
                              ("artifact_size",1),("sequence",0),("key_id","fake")):
                with self.subTest(field=key):
                    with self.assertRaises(FrozenInstanceError):
                        setattr(m,key,value)
                    with self.assertRaises(TypeError):
                        m[key]=value
            with self.assertRaises(FrozenInstanceError):
                m.unsigned_extension={"privileged":True}
            with self.assertRaises(KeyError):
                _=m["unsigned_extension"]
            with self.assertRaises(FrozenInstanceError):
                f.metadata={"platform":"windows"}
            with self.assertRaises(FrozenInstanceError):
                f._verified_length=1
            with self.assertRaises(FrozenInstanceError):
                f._fd=-1
            self.assertEqual(f.read(),GOOD)

    def test_03_nested_signed_structures_are_rejected_even_if_signed(self):
        for mutation in (
            {"platform":{"nested":"linux"}},
            {"artifact_size":[len(GOOD)]},
            {"architecture":["x86_64"]},
            {"sequence":{"v":23}},
            {"key_id":["key"]},
            {"source_commit":{"hex":"f"*40}},
            {"extra":{"children":[1,2]}},
        ):
            with self.subTest(mutation=mutation):
                raw,sig=self.envelope({**self.fields,**mutation})
                with self.assertRaises(gate.TrustRejected):
                    with self.accept(raw,sig):
                        self.fail("Untrusted nested/unknown signed fields were accepted")

    def test_04_returned_mutable_copies_cannot_change_verified_policy(self):
        with self.accept() as f:
            m=f.metadata
            copies=[m.to_dict(),f.metadata_copy(),dict(m)]
            for copy in copies:
                copy["platform"]="windows"
                copy["artifact_size"]=1
                copy["sequence"]=0
                copy["extra"]={"nested":{"permissions":["all"]}}
                copy["extra"]["nested"]["permissions"].append("root")
            self.assertEqual(m.platform,"linux")
            self.assertEqual(m.artifact_size,len(GOOD))
            self.assertEqual(m.sequence,23)
            self.assertNotIn("extra",m)
            self.assertEqual(f.read(),GOOD)

    def test_05_caller_original_json_dict_does_not_alias_verified_snapshot(self):
        mutable=dict(self.fields)
        raw,sig=self.envelope(mutable)
        with self.accept(raw,sig) as f:
            mutable.update(platform="windows",artifact_size=1,sequence=0)
            mutable["extra"]={"nested":[1,2]}
            self.assertEqual(f.metadata["platform"],"linux")
            self.assertEqual(f.metadata["artifact_size"],len(GOOD))
            self.assertEqual(f.metadata["sequence"],23)
            self.assertEqual(f.verified_length,len(GOOD))
            self.assertEqual(f.read(),GOOD)

    def test_06_pread_is_exactly_verified_size_despite_export_copy(self):
        with self.accept() as f:
            e=f.metadata_copy()
            e["artifact_size"]=1
            original=os.pread
            calls=[]
            def spy(fd,n,offset):
                calls.append((fd,n,offset))
                return original(fd,n,offset)
            with patch.object(gate.os,"pread",new=spy):
                data=f.read()
            self.assertEqual(data,GOOD)
            self.assertEqual(calls,[(f.fd,len(GOOD),0)])

    def test_07_fd_stat_length_drift_is_refused(self):
        with self.accept() as f:
            original=os.fstat
            def corrupt(fd):
                result=original(fd)
                if fd!=f.fd:
                    return result
                class Fake:
                    st_size=result.st_size+1
                return Fake()
            with patch.object(gate.os,"fstat",new=corrupt):
                with self.assertRaisesRegex(gate.TrustRejected,"length"):
                    f.read()
            self.assertEqual(f.read(),GOOD)

    def test_08_short_pread_fails_even_with_matching_fd_stat(self):
        with self.accept() as f:
            with patch.object(gate.os,"pread",return_value=GOOD[:-1]):
                with self.assertRaisesRegex(gate.TrustRejected,"Truncated"):
                    f.read()
            self.assertEqual(f.read(),GOOD)

    def test_09_full_linux_seals_reject_writes_truncate_and_mmap(self):
        with self.accept() as f:
            required=(fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|
                      fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
            self.assertEqual(fcntl.fcntl(f.fd,fcntl.F_GET_SEALS)&required,required)
            with self.assertRaises(OSError):
                os.pwrite(f.fd,b"bad",0)
            with self.assertRaises(OSError):
                os.ftruncate(f.fd,0)
            with self.assertRaises((OSError,ValueError)):
                mmap.mmap(f.fd,len(GOOD),access=mmap.ACCESS_WRITE)
            self.assertEqual(f.read(),GOOD)

    def test_10_source_path_swap_after_single_open_preserves_signed_bytes(self):
        original=gate._open_source_once
        moved=self.root/"old-pinned-artifact"
        observed=[]
        def attack(path,runner):
            fd=original(path,runner)
            observed.append(True)
            self.file.rename(moved)
            self.file.write_bytes(b"FOREIGN-CONTENT")
            return fd
        with patch.object(gate,"_open_source_once",new=attack):
            with self.accept() as f:
                self.assertEqual(f.read(),GOOD)
        self.assertEqual(len(observed),1)
        self.assertEqual(moved.read_bytes(),GOOD)
        self.assertEqual(self.file.read_bytes(),b"FOREIGN-CONTENT")

    def test_11_same_inode_mutation_after_open_fails_closed(self):
        original=gate._open_source_once
        calls=[]
        def attack(path,runner):
            fd=original(path,runner)
            calls.append(True)
            self.file.write_bytes(b"WRONG-IN-PLACE")
            return fd
        with patch.object(gate,"_open_source_once",new=attack):
            with self.assertRaises(gate.TrustRejected):
                self.accept()
        self.assertEqual(len(calls),1)

    def test_12_close_is_idempotent_and_read_after_close_fails(self):
        obj=self.accept()
        old=obj.fd
        self.assertEqual(obj.read(),GOOD)
        obj.close()
        obj.close()
        with self.assertRaises(OSError):
            os.fstat(old)
        with self.assertRaisesRegex(gate.TrustRejected,"closed"):
            obj.read()
        with self.assertRaisesRegex(gate.TrustRejected,"closed"):
            _=obj.fd

    def test_13_verified_fixture_length_and_metadata_mismatch_constructor_rejects(self):
        with self.accept() as f:
            with self.assertRaisesRegex(gate.TrustRejected,"Inconsistent"):
                gate.SealedFixture(f.fd,f.metadata,1)
            with self.assertRaisesRegex(gate.TrustRejected,"Inconsistent"):
                gate.SealedFixture(f.fd,{"artifact_size":len(GOOD)},len(GOOD))
            with self.assertRaisesRegex(gate.TrustRejected,"Inconsistent"):
                gate.SealedFixture(f.fd,f.metadata,True)
            self.assertEqual(f.read(),GOOD)

    def test_14_original_20_attacks_still_present_and_new_negative_18(self):
        source=Path(__file__).with_name("flight_pr37_independent_security_qa.py").read_text()
        for num in range(1,21):
            self.assertIn(f"def test_{num:02d}_",source)
        self.assertIn("test_18_verified_metadata_is_frozen_and_read_length_pinned",source)
        self.assertNotIn("test_18_sealed_result_exposes_mutable_metadata_dictionary",source)
        # Positive tests for STILL OPEN P1 trust policies remain in inherited QA.
        self.assertIn("test_08_external_caller_key_origin_is_a_trust_boundary",source)
        self.assertIn("test_19_trusted_time_is_caller_policy",source)

    def test_15_public_constructor_can_wrap_unsigned_unsealed_fd_positive_gap(self):
        # POSITIVE P2: a direct constructor accepts a fabricated "verified"
        # metadata record with no signature check and a REGULAR FILE FD
        # without inspecting required seal flags or matching digest.
        # No production installer uses it; a future trust API MUST NOT
        # equate the object type with an authenticated/sealed provenance.
        forged=gate.VerifiedMetadata(**{**self.fields,"platform":"windows",
                                        "artifact_sha256":"0"*64})
        ordinary=os.open(self.file,os.O_RDONLY|os.O_CLOEXEC)
        with gate.SealedFixture(ordinary,forged,len(GOOD)) as fabricated:
            self.assertEqual(fabricated.metadata.platform,"windows")
            self.assertEqual(fabricated.read(),GOOD)
            with self.assertRaises(OSError):
                fcntl.fcntl(fabricated.fd,fcntl.F_GET_SEALS)

    def test_16_closed_exposed_fd_reuse_returns_foreign_bytes_positive_gap(self):
        # POSITIVE P2: downstream can os.close(exposed_fd), and the kernel
        # may recycle the descriptor number for an unrelated unsealed file.
        # read() checks ONLY length, not FD identity/seals/digest on every
        # call. This is NOT a bypass of a still-open sealed memfd.
        forged_path=self.root/"foreign-reused-fd"
        forged_bytes=b"X"*len(GOOD)
        forged_path.write_bytes(forged_bytes)
        with self.accept() as artifact:
            number=artifact.fd
            os.close(number)
            foreign=os.open(forged_path,os.O_RDONLY|os.O_CLOEXEC)
            if foreign!=number:
                os.dup2(foreign,number)
                os.close(foreign)
            self.assertEqual(os.fstat(number).st_size,len(GOOD))
            self.assertEqual(artifact.read(),forged_bytes)
            artifact.close()
            with self.assertRaises(OSError):
                os.fstat(number)

    def test_17_frozen_python_fields_low_level_setattr_is_not_os_security(self):
        # POSITIVE documented threat boundary: dataclass frozen is an
        # accident-resistance API control, not a same-interpreter policy
        # enforcement mechanism against arbitrary hostile Python code.
        with self.accept() as f:
            m=f.metadata
            object.__setattr__(m,"platform","windows")
            object.__setattr__(m,"artifact_size",1)
            self.assertEqual(m.platform,"windows")
            self.assertEqual(f.read(),GOOD)
            self.assertEqual(f.verified_length,len(GOOD))


if __name__=="__main__":
    unittest.main(verbosity=2)
