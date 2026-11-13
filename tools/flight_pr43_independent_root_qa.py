#!/usr/bin/env python3
"""Independent Agent 06 P1-root/provenance PR43 security QA.

Only GitHub-hosted disposable Linux CI. Synthetic Ed25519 keys are generated
in RAM, never stored, exported, installed or deemed production authorities.

Tests named POSITIVE_GAP deliberately PASS by demonstrating a limitation;
a green CI run is *not* authorization for production distribution.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
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
from tools import flight_root_provenance_ci as authority
from tools import flight_signed_installer_ci_prototype as fixture


NOW = 1800000000
SIGNED = b"INDEPENDENT-PR43-ROOT-SOURCE-BUILD-PACKAGE"
ALIEN = b"X" * len(SIGNED)


def pub(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


@unittest.skipUnless(os.name == "posix", "Linux-only sealed fixture")
class PR43IndependentQA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI") != "true"
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Disposable GitHub-hosted Linux CI ONLY")
        self.temp = tempfile.TemporaryDirectory(
            dir=os.environ["RUNNER_TEMP"], prefix="flight-pr43-independent-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "signed-data.bin"
        self.file.write_bytes(SIGNED)
        self.file.chmod(0o600)
        self.root_sk = Ed25519PrivateKey.generate()
        self.release_sk = Ed25519PrivateKey.generate()
        self.builder_sk = Ed25519PrivateKey.generate()
        self.anchor = authority.RootAnchor("fixture-root",pub(self.root_sk),1,3)
        self.root_policy = {
            "schema":1, "root_id":"fixture-root",
            "root_public_key":pub(self.root_sk).hex(),
            "epoch":1, "version":3, "expires_at":NOW+100,
            "app_id":fixture.APP_ID, "channel":fixture.CHANNEL,
            "source_repo":authority.SOURCE,"workflow":"independent-build",
            "minimum_release_sequence":20,
            "signers":[self.signer("release1",self.release_sk,"release"),
                       self.signer("builder1",self.builder_sk,"builder")],
            "revoked_key_ids":[]
        }
        self.manifest = {
            "schema":1,"app_id":fixture.APP_ID,"channel":fixture.CHANNEL,
            "platform":"linux","architecture":"x86_64",
            "artifact_name":self.file.name,
            "artifact_size":len(SIGNED),
            "artifact_sha256":hashlib.sha256(SIGNED).hexdigest(),
            "sequence":25, "issued_at":NOW-100,"expires_at":NOW+100,
            "source_commit":"c"*40, "key_id":"release1"
        }
        self.build = {
            "schema":1,"builder_id":"builder1",
            "source_repo":authority.SOURCE,
            "source_commit":"c"*40,
            "workflow":"independent-build","run_id":"run1","build_id":"build1",
            "app_id":fixture.APP_ID,"channel":fixture.CHANNEL,
            "platform":"linux","architecture":"x86_64",
            "artifact_name":self.file.name,
            "artifact_size":len(SIGNED),
            "artifact_sha256":hashlib.sha256(SIGNED).hexdigest(),
            "release_sequence":25,"issued_at":NOW-100,"expires_at":NOW+100
        }

    def signer(self,key_id,key,role):
        return {"key_id":key_id,"public_key":pub(key).hex(),
                "role":role,"platform":"linux","architecture":"x86_64",
                "expires_at":NOW+200}

    def envelopes(self,*,policy=None,manifest=None,build=None,root_sk=None,
                  release_sk=None,builder_sk=None):
        rr=fixture.canonical_bytes(self.root_policy if policy is None else policy)
        mr=fixture.canonical_bytes(self.manifest if manifest is None else manifest)
        br=fixture.canonical_bytes(self.build if build is None else build)
        return (rr,(self.root_sk if root_sk is None else root_sk).sign(
                authority.ROOT_DOMAIN+rr),
                mr,(self.release_sk if release_sk is None else release_sk).sign(
                fixture.DOMAIN+mr),
                br,(self.builder_sk if builder_sk is None else builder_sk).sign(
                authority.BUILD_DOMAIN+br))

    def approve(self,*,envelopes=None,anchor=None,now=NOW,floor=20,
                platform="linux",arch="x86_64",seal=False):
        rr,rs,mr,ms,br,bs=(self.envelopes() if envelopes is None else envelopes)
        a=self.anchor if anchor is None else anchor
        if seal:
            return authority.verify_provenance_and_seal(
                self.file,rr,rs,a,mr,ms,br,bs,
                minimum_sequence=floor,now=now)
        return authority.verify_release_provenance(
            rr,rs,a,mr,ms,br,bs,
            platform=platform,architecture=arch,
            minimum_sequence=floor,now=now)

    def test_01_expected_good_root_release_builder_chain(self):
        approval=self.approve()
        self.assertEqual(approval.root_id,"fixture-root")
        self.assertEqual(approval.root_version,3)
        self.assertEqual(approval.release.artifact_sha256,
                         hashlib.sha256(SIGNED).hexdigest())
        self.assertEqual(approval.builder_id,"builder1")
        with self.assertRaises(FrozenInstanceError):
            approval.builder_id="attacker"

    def test_02_attacker_signed_root_rejected_by_unchanged_pin(self):
        rogue=Ed25519PrivateKey.generate()
        changed={**self.root_policy,"root_public_key":pub(rogue).hex()}
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(envelopes=self.envelopes(policy=changed,root_sk=rogue))

    def test_03_POSITIVE_GAP_attacker_controlled_root_pin_self_authorizes(self):
        rogue=Ed25519PrivateKey.generate()
        changed={**self.root_policy,"root_public_key":pub(rogue).hex()}
        fake_anchor=authority.RootAnchor("fixture-root",pub(rogue),1,3)
        accepted=self.approve(envelopes=self.envelopes(
            policy=changed,root_sk=rogue),anchor=fake_anchor)
        self.assertEqual(accepted.root_id,fake_anchor.root_id)
        self.assertNotEqual(fake_anchor.public_key,self.anchor.public_key)

    def test_04_tampered_root_metadata_original_signature_rejected(self):
        e=list(self.envelopes())
        e[0]=fixture.canonical_bytes({**self.root_policy,"minimum_release_sequence":0})
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(envelopes=tuple(e))

    def test_05_signed_wrong_root_app_and_source_policy_rejected(self):
        for changed in (
            {"source_repo":"malicious/repo"},
            {"app_id":"fake-app"},
            {"channel":"production"},
        ):
            with self.subTest(change=changed):
                with self.assertRaises(authority.AuthorityRejected):
                    self.approve(envelopes=self.envelopes(
                        policy={**self.root_policy,**changed}))

    def test_06_noncanonical_duplicate_unknown_root_policy_rejected(self):
        rr,rs,mr,ms,br,bs=self.envelopes()
        for raw in (rr[:-1]+b',"schema":1}',
                    json.dumps(self.root_policy,sort_keys=True).encode(),
                    fixture.canonical_bytes({**self.root_policy,
                                             "unreviewed":{"root":"yes"}})):
            with self.subTest(raw=raw[:30]):
                signature=self.root_sk.sign(authority.ROOT_DOMAIN+raw)
                with self.assertRaises(fixture.TrustRejected):
                    self.approve(envelopes=(raw,signature,mr,ms,br,bs))

    def test_07_signer_role_confusion_rejected(self):
        bad_manifest={**self.manifest,"key_id":"builder1"}
        bad_build={**self.build,"builder_id":"release1"}
        for e in (self.envelopes(manifest=bad_manifest),
                  self.envelopes(build=bad_build)):
            with self.assertRaises(authority.AuthorityRejected):
                self.approve(envelopes=e)

    def test_08_unknown_or_forged_release_builder_signatures_rejected(self):
        rogue=Ed25519PrivateKey.generate()
        for e in (self.envelopes(release_sk=rogue),
                  self.envelopes(builder_sk=rogue),
                  self.envelopes(build={**self.build,"builder_id":"unknown"})):
            with self.assertRaises(authority.AuthorityRejected):
                self.approve(envelopes=e)

    def test_09_signer_keys_root_key_must_not_reuse_material(self):
        for signers in (
            [self.signer("release1",self.root_sk,"release"),
             self.root_policy["signers"][1]],
            [self.root_policy["signers"][0],
             self.signer("builder1",self.release_sk,"builder")],
            [self.signer("release1",self.release_sk,"release"),
             self.signer("release1",self.builder_sk,"builder")],
        ):
            with self.subTest(keys=signers):
                with self.assertRaises(authority.AuthorityRejected):
                    self.approve(envelopes=self.envelopes(
                        policy={**self.root_policy,"signers":signers}))

    def test_10_revoked_and_expired_signers_denied(self):
        future=Ed25519PrivateKey.generate()
        p={**self.root_policy,
           "revoked_key_ids":["release1"],
           "signers":[self.signer("release2",future,"release"),
                      self.root_policy["signers"][1]]}
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(envelopes=self.envelopes(policy=p))
        expired={**self.root_policy,
                 "signers":[{**self.root_policy["signers"][0],
                            "expires_at":NOW-1},
                            self.root_policy["signers"][1]]}
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(envelopes=self.envelopes(policy=expired))

    def test_11_root_expiry_and_independent_epoch_version_floor(self):
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(now=NOW+101)
        bad_anchor=authority.RootAnchor("fixture-root",pub(self.root_sk),2,4)
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(anchor=bad_anchor)

    def test_12_dual_old_and_new_root_signatures_accepted(self):
        new=Ed25519PrivateKey.generate()
        p={**self.root_policy,"epoch":2,"version":4,
           "root_public_key":pub(new).hex()}
        raw=fixture.canonical_bytes(p)
        oldsig=self.root_sk.sign(authority.ROOT_DOMAIN+raw)
        newsig=new.sign(authority.ROOT_DOMAIN+raw)
        next_anchor=authority.rotate_root_anchor(
            self.anchor,raw,oldsig,newsig,now=NOW)
        self.assertEqual((next_anchor.minimum_epoch,next_anchor.minimum_version),(2,4))
        self.assertEqual(next_anchor.public_key,pub(new))

    def test_13_invalid_old_or_new_rotation_signature_rejected(self):
        new=Ed25519PrivateKey.generate()
        rogue=Ed25519PrivateKey.generate()
        p={**self.root_policy,"epoch":2,"version":4,
           "root_public_key":pub(new).hex()}
        raw=fixture.canonical_bytes(p)
        oldsig=self.root_sk.sign(authority.ROOT_DOMAIN+raw)
        newsig=new.sign(authority.ROOT_DOMAIN+raw)
        for o,n in (
            (rogue.sign(authority.ROOT_DOMAIN+raw),newsig),
            (oldsig,rogue.sign(authority.ROOT_DOMAIN+raw))):
            with self.assertRaises(authority.AuthorityRejected):
                authority.rotate_root_anchor(self.anchor,raw,o,n,now=NOW)

    def test_14_rotation_wrong_epoch_version_and_root_replay_rejected(self):
        new=Ed25519PrivateKey.generate()
        for version,epoch in ((3,2),(4,1),(5,2),(4,3)):
            p={**self.root_policy,"epoch":epoch,"version":version,
               "root_public_key":pub(new).hex()}
            raw=fixture.canonical_bytes(p)
            with self.assertRaises(authority.AuthorityRejected):
                authority.rotate_root_anchor(
                    self.anchor,raw,
                    self.root_sk.sign(authority.ROOT_DOMAIN+raw),
                    new.sign(authority.ROOT_DOMAIN+raw),now=NOW)

    def test_15_POSITIVE_GAP_revoked_signer_reactivated_by_rotation(self):
        """Newly found: previous root's revocation ledger is not in RootAnchor.
        After legitimate dual-sign rotation, signer revoked in old signed
        policy can appear as active in the new signed policy.
        """
        replacement=Ed25519PrivateKey.generate()
        old={**self.root_policy,
             "revoked_key_ids":["builder1"],
             "signers":[self.root_policy["signers"][0],
                        self.signer("builder2",replacement,"builder")]}
        old_raw=fixture.canonical_bytes(old)
        old_sig=self.root_sk.sign(authority.ROOT_DOMAIN+old_raw)
        validated=authority.verify_root_policy(old_raw,old_sig,self.anchor,now=NOW)
        self.assertIn("builder1",validated.revoked_key_ids)
        future=Ed25519PrivateKey.generate()
        resurrected={**self.root_policy,
                     "epoch":2,"version":4,"root_public_key":pub(future).hex(),
                     "revoked_key_ids":[],
                     "signers":self.root_policy["signers"]}
        rr=fixture.canonical_bytes(resurrected)
        anchor2=authority.rotate_root_anchor(
            self.anchor,rr,
            self.root_sk.sign(authority.ROOT_DOMAIN+rr),
            future.sign(authority.ROOT_DOMAIN+rr),
            now=NOW)
        approved=self.approve(
            envelopes=self.envelopes(policy=resurrected,root_sk=future),
            anchor=anchor2)
        self.assertEqual(approved.builder_id,"builder1")
        self.assertNotIn("builder1",
                         authority.verify_root_policy(
                             rr,future.sign(authority.ROOT_DOMAIN+rr),
                             anchor2,now=NOW).revoked_key_ids)

    def test_16_POSITIVE_GAP_expired_previous_root_can_rotate(self):
        """Newly found: rotate_root_anchor does not consume authenticated
        prior root policy/expiration and relies on the bare pin alone.
        """
        stale={**self.root_policy,"expires_at":NOW-1}
        sr=fixture.canonical_bytes(stale)
        old_root=authority.verify_root_policy(
            sr,self.root_sk.sign(authority.ROOT_DOMAIN+sr),
            self.anchor,now=NOW-2)
        self.assertEqual(old_root.root_id,"fixture-root")
        new=Ed25519PrivateKey.generate()
        future={**self.root_policy,"epoch":2,"version":4,
                "root_public_key":pub(new).hex(),"expires_at":NOW+1000}
        rr=fixture.canonical_bytes(future)
        anchor2=authority.rotate_root_anchor(
            self.anchor,rr,self.root_sk.sign(authority.ROOT_DOMAIN+rr),
            new.sign(authority.ROOT_DOMAIN+rr),now=NOW)
        self.assertEqual(anchor2.minimum_version,4)

    def test_17_false_build_repo_workflow_and_commit_mismatch_rejected(self):
        for changes in (
            {"source_repo":"other/repo"},
            {"workflow":"evil-runner"},
            {"source_commit":"f"*40},
            {"run_id":"new-run","release_sequence":0},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(authority.AuthorityRejected):
                    self.approve(envelopes=self.envelopes(build={
                        **self.build,**changes}))

    def test_18_artifact_hash_length_and_name_mismatch_in_builder_denied(self):
        for changes in (
            {"artifact_sha256":"0"*64},
            {"artifact_size":len(SIGNED)+1},
            {"artifact_name":"other.bin"},
        ):
            with self.assertRaises(authority.AuthorityRejected):
                self.approve(envelopes=self.envelopes(build={
                    **self.build,**changes}))

    def test_19_POSITIVE_LIMIT_authorized_builder_can_lie_about_build_origin(self):
        """Signed mutually consistent commit/run claims aren't attestation
        that a real isolated builder actually ran the claimed source.
        """
        m={**self.manifest,"source_commit":"e"*40}
        b={**self.build,"source_commit":"e"*40,
           "run_id":"fictional-run","build_id":"fictional-build"}
        approved=self.approve(envelopes=self.envelopes(manifest=m,build=b))
        self.assertEqual(approved.release.source_commit,"e"*40)
        self.assertEqual(approved.run_id,"fictional-run")

    def test_20_POSITIVE_LIMIT_old_valid_release_replays_when_floor_stale(self):
        a=self.approve()
        b=self.approve()
        self.assertEqual(a.release.sequence,b.release.sequence)

    def test_21_actual_signed_bytes_handoff_and_four_seals(self):
        with self.approve(seal=True) as result:
            self.assertEqual(result.read(),SIGNED)
            self.assertFalse(hasattr(result,"fd"))
            self.assertEqual(result.verified_length,len(SIGNED))
            fd=result._fd  # WHITE-BOX only; not public API
            self.assertEqual(fcntl.fcntl(fd,fcntl.F_GET_SEALS)
                &fixture._REQUIRED_SEALS,fixture._REQUIRED_SEALS)
            self.assertEqual(result.metadata["artifact_sha256"],
                             hashlib.sha256(SIGNED).hexdigest())

    def test_22_renamed_source_after_single_open_keeps_original_bytes(self):
        old_open=fixture._open_source_once
        moved=self.root/"pinned-signed-original"
        touched=[]
        def redirect(path,runner):
            fd=old_open(path,runner)
            touched.append(True)
            self.file.rename(moved)
            self.file.write_bytes(ALIEN)
            return fd
        with patch.object(fixture,"_open_source_once",new=redirect):
            with self.approve(seal=True) as result:
                self.assertEqual(result.read(),SIGNED)
        self.assertEqual(touched,[True])
        self.assertEqual(moved.read_bytes(),SIGNED)

    def test_23_inplace_same_inode_source_mutation_rejected(self):
        old_open=fixture._open_source_once
        def attack(path,runner):
            fd=old_open(path,runner)
            self.file.write_bytes(ALIEN)
            return fd
        with patch.object(fixture,"_open_source_once",new=attack):
            with self.assertRaises(fixture.TrustRejected):
                self.approve(seal=True)

    def test_24_hash_mismatch_with_signed_release_fails_handoff(self):
        self.file.write_bytes(ALIEN)
        self.file.chmod(0o600)
        with self.assertRaises(fixture.TrustRejected):
            self.approve(seal=True)

    def test_25_mocked_corrupted_sealed_read_fails_closed(self):
        with self.approve(seal=True) as result:
            original=os.pread
            def attack(fd,n,offset):
                if fd==result._fd:
                    return ALIEN
                return original(fd,n,offset)
            with patch.object(fixture.os,"pread",new=attack):
                with self.assertRaisesRegex(fixture.TrustRejected,"digest"):
                    result.read()
            self.assertEqual(result.read(),SIGNED)

    def test_26_expired_builder_attestation_denied_with_valid_release(self):
        with self.assertRaises(authority.AuthorityRejected):
            self.approve(envelopes=self.envelopes(
                build={**self.build,"expires_at":NOW-1}))

    def test_27_nested_signed_root_role_extension_rejected(self):
        changed={**self.root_policy,
                 "signers":[{**self.root_policy["signers"][0],
                             "roles":["builder","release"]},
                            self.root_policy["signers"][1]]}
        with self.assertRaises(fixture.TrustRejected):
            self.approve(envelopes=self.envelopes(policy=changed))

    def test_28_test_keys_are_ephemeral_only_and_production_bootstrap_absent(self):
        self.assertTrue(self.root_sk is not self.release_sk)
        self.assertTrue(self.release_sk is not self.builder_sk)
        self.assertNotEqual(pub(self.root_sk),pub(self.builder_sk))
        self.assertIn("CALLER",authority.__doc__)
        self.assertNotIn("private_key",self.root_policy)
