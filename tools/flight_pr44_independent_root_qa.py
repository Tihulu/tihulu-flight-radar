#!/usr/bin/env python3
"""Agent 06 independent PR #44 P1 trust-root/provenance adversarial QA.

EXACT AUDITED PR #44: ea67f3f679adc813ae84193307d4b253f42d8fd7.
Ported independent PR #45 positive witnesses #15/#16 to this entirely
different signed quorum-policy API as STRICT NEGATIVE acceptance tests:
  - revoked signer cannot resurrect in a validly old+new signed rotation
  - expired old authenticated root cannot cross-sign a fresh new root.
Other POSITIVE_LIMIT tests demonstrate acknowledged production P1 blockers.
Never use temporary in-RAM keys as real root/release signing authority.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import flight_p1_root_provenance_ci as gate

NOW=1800000000
CONTENT=b"INDEPENDENT-PR44-SIGNED-ARTIFACT-FIXTURE"
COMMIT="c"*40
TREE="d"*64
RECIPE="e"*64
MATERIALS="f"*64
SOURCE="github.com/Tihulu/tihulu-flight-radar"
REF="refs/heads/main"
WORKFLOW="github.com/Tihulu/tihulu-flight-radar/.github/workflows/release.yml"


def public_hex(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw).hex()


@unittest.skipUnless(os.name=="posix", "Disposable Linux-only CI fixture")
class IndependentPR44QA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI")!="true" or
                os.environ.get("GITHUB_ACTIONS")!="true" or
                not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Only disposable GitHub-hosted CI")
        self.temp=tempfile.TemporaryDirectory(
            prefix="agent06-pr44-",dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.keys={name:Ed25519PrivateKey.generate() for name in (
            "root1","root2","root3","root4",
            "source1","source2","builder1","builder2","release1","release2",
            "attacker1","attacker2","attacker3")}
        self.initial=self.make_policy()
        self.pins=gate.pin_bootstrap_roots(
            self.initial["root_keys"],2,
            gate.pin_digest(self.initial["root_keys"],2))
        self.original=self.auth_root(self.initial)

    def root_map(self, *names):
        return {name:public_hex(self.keys[name]) for name in names}

    def make_policy(self, *, version=1, root_ids=("root1","root2","root3"),
                    revoked=(), source_ids=("source1",),
                    builder_ids=("builder1",), release_ids=("release1",),
                    issued_at=NOW-1000, expires_at=NOW+1000):
        return {
            "schema":1,"domain":gate.TRUST_DOMAIN,"version":version,
            "issued_at":issued_at,"expires_at":expires_at,
            "threshold":2,"root_keys":self.root_map(*root_ids),
            "role_keys":{
                "source":self.root_map(*source_ids),
                "builder":self.root_map(*builder_ids),
                "release":self.root_map(*release_ids),
            },
            "revoked_key_ids":sorted(revoked),
            "source_repo":SOURCE,"source_ref":REF,
            "builder_workflow":WORKFLOW,
        }

    def sign_root(self, policy, signers=("root1","root2")):
        raw=gate.canonical(policy)
        signed={name:self.keys[name].sign(gate.ROOT_DOMAIN+raw).hex()
                for name in signers}
        return raw,signed

    def auth_root(self, policy, signers=("root1","root2"), *,
                  previous=None, bootstrap=None, now=NOW, minimum=None):
        raw,signed=self.sign_root(policy,signers)
        return gate.verify_root_policy(raw,signed,now=now,
            minimum_version=(policy["version"] if minimum is None else minimum),
            bootstrap=(self.pins if bootstrap is None else bootstrap)
            if previous is None else None,previous=previous)

    def new_policy(self, **changes):
        default=self.make_policy(
            version=2,root_ids=("root2","root3","root4"),
            revoked=("root1",),issued_at=NOW-800,expires_at=NOW+1000)
        default.update(changes)
        return default

    def rotate(self, policy=None, signers=("root1","root2","root4"),
               *,previous=None,now=NOW,minimum=2):
        return self.auth_root(
            self.new_policy() if policy is None else policy,
            signers,previous=self.original if previous is None else previous,
            now=now,minimum=minimum)

    def sign_document(self, document, keyid, domain):
        raw=gate.canonical(document)
        return raw,self.keys[keyid].sign(domain+raw).hex()

    def bundle(self,root=None,*, source_updates=None,builder_updates=None,
               release_updates=None,source_signer="source1",
               builder_signer="builder1",release_signer="release1",
               artifact=CONTENT):
        root=self.original if root is None else root
        src={"schema":1,"key_id":source_signer,
             "repo":SOURCE,"ref":REF,
             "commit":COMMIT,"tree_sha256":TREE}
        if source_updates:
            src.update(source_updates)
        sr,ss=self.sign_document(src,source_signer,gate.SOURCE_DOMAIN)
        built={
            "schema":1,"key_id":builder_signer,
            "repo":src["repo"],"ref":src["ref"],"commit":src["commit"],
            "tree_sha256":src["tree_sha256"],
            "source_attestation_sha256":hashlib.sha256(sr).hexdigest(),
            "artifact_sha256":hashlib.sha256(artifact).hexdigest(),
            "artifact_size":len(artifact),"recipe_sha256":RECIPE,
            "materials_sha256":MATERIALS,
            "builder_workflow":WORKFLOW,
        }
        if builder_updates:
            built.update(builder_updates)
        br,bs=self.sign_document(built,builder_signer,gate.BUILDER_DOMAIN)
        release={
            "schema":1,"key_id":release_signer,"root_version":root.version,
            "app_id":gate.APP,"channel":gate.CHANNEL,
            "platform":"linux","architecture":"x86_64",
            "artifact_name":"independent-pr44.bin",
            "artifact_size":built["artifact_size"],
            "artifact_sha256":built["artifact_sha256"],"sequence":9,
            "repo":built["repo"],"ref":built["ref"],
            "commit":built["commit"],"tree_sha256":built["tree_sha256"],
            "recipe_sha256":built["recipe_sha256"],
            "materials_sha256":built["materials_sha256"],
            "source_attestation_sha256":built["source_attestation_sha256"],
            "builder_attestation_sha256":hashlib.sha256(br).hexdigest()
        }
        if release_updates:
            release.update(release_updates)
        rr,rs=self.sign_document(release,release_signer,gate.RELEASE_DOMAIN)
        return dict(root=root,
            source_raw=sr,source_signature=ss,
            builder_raw=br,builder_signature=bs,
            release_raw=rr,release_signature=rs,
            artifact=artifact,expected_commit=COMMIT,
            expected_tree_sha256=TREE,
            expected_platform="linux",expected_arch="x86_64",
            minimum_sequence=9,minimum_root_version=root.version,now=NOW)

    def check(self,payload=None,**changes):
        b=self.bundle() if payload is None else dict(payload)
        b.update(changes)
        return gate.verify_provenance_bundle(**b)

    def test_01_legitimate_2of3_independently_pinned_root_and_verified_artifact(self):
        self.assertEqual(self.original.version,1)
        self.assertEqual(self.original.threshold,2)
        rec=self.check()
        self.assertEqual(rec.artifact_sha256,hashlib.sha256(CONTENT).hexdigest())
        self.assertEqual(rec.artifact_size,len(CONTENT))
        self.assertEqual(rec.source_commit,COMMIT)
        self.assertEqual(rec.tree_sha256,TREE)
        with self.assertRaises((TypeError,FrozenInstanceError)):
            rec.root_version=44

    def test_02_strict_bootstrap_pin_fingerprint_and_exact_roster(self):
        with self.assertRaisesRegex(gate.TrustRejected,"differs"):
            gate.pin_bootstrap_roots(
                self.initial["root_keys"],2,"0"*64)
        changed={**self.initial,"root_keys":self.root_map(
            "root1","root2","attacker1")}
        with self.assertRaisesRegex(gate.TrustRejected,"exactly match"):
            self.auth_root(changed,signers=("root1","root2"))

    def test_03_one_root_or_nonroot_endorser_cannot_satisfy_threshold(self):
        for signers in (("root1",),("source1",),("builder1",)):
            with self.subTest(signers=signers):
                with self.assertRaises(gate.TrustRejected):
                    self.auth_root(self.initial,signers=signers)

    def test_04_two_of_three_independent_root_signers_enough(self):
        approved=self.auth_root(self.initial,signers=("root2","root3"))
        self.assertEqual(approved.version,1)

    def test_05_root_policy_signature_tamper_and_duplicate_json_rejected(self):
        rr,sig=self.sign_root(self.initial)
        changed=rr.replace(b'"version":1',b'"version":2')
        with self.assertRaises(gate.TrustRejected):
            gate.verify_root_policy(changed,sig,now=NOW,
                minimum_version=1,bootstrap=self.pins)
        duplicate=rr[:-1]+b',"version":1}'
        signed={k:self.keys[k].sign(gate.ROOT_DOMAIN+duplicate).hex()
                for k in ("root1","root2")}
        with self.assertRaisesRegex(gate.TrustRejected,"Duplicate"):
            gate.verify_root_policy(duplicate,signed,now=NOW,
                minimum_version=1,bootstrap=self.pins)

    def test_06_dual_quorum_old_and_new_honestly_signed_rotation_accepted(self):
        result=self.rotate()
        self.assertEqual(result.version,2)
        self.assertEqual(set(result.root_keys),{"root2","root3","root4"})
        self.assertIn("root1",result.revoked_key_ids)

    def test_07_old_root_quorum_missing_rejected_even_if_new_quorum_present(self):
        with self.assertRaisesRegex(gate.TrustRejected,
                                    "Previous trusted root threshold"):
            self.rotate(signers=("root2","root4"))

    def test_08_new_root_quorum_missing_rejected_even_if_old_quorum_present(self):
        with self.assertRaisesRegex(gate.TrustRejected,"New root threshold"):
            self.rotate(signers=("root1","root2"))

    def test_09_root_rotation_signed_epoch_wrong_version_or_downgrade_rejected(self):
        for version in (1,3,0):
            with self.subTest(version=version):
                changed=self.new_policy(version=version)
                with self.assertRaises(gate.TrustRejected):
                    self.rotate(changed)

    def test_10_explicit_revocation_of_removed_old_root_key_required(self):
        bad=self.new_policy(revoked_key_ids=[])
        with self.assertRaisesRegex(gate.TrustRejected,"Retired authority"):
            self.rotate(bad)

    def test_11_P2_F43_01_revoked_builder_resurrection_rejected_with_valid_quorums(self):
        """Port PR #45 test_15: old valid root revokes builder1; new policy
        *reintroduces builder1 with valid OLD+NEW root signatures* while
        deleting its old revocation. Must reject for REVOCATION CONTINUITY,
        not merely unsigned policy, missing signer or invalid version.
        """
        old=self.make_policy(
            revoked=("builder1",),builder_ids=("builder2",))
        previous=self.auth_root(old)
        self.assertIn("builder1",previous.revoked_key_ids)
        self.assertNotIn("builder1",previous.role_keys["builder"])
        new=self.new_policy(
            revoked_key_ids=["builder2","root1"],
            role_keys={**self.initial["role_keys"],
                       "builder":self.root_map("builder1")})
        with self.assertRaisesRegex(gate.TrustRejected,
                                    "revocation ledger cannot shrink"):
            self.rotate(new,previous=previous)
        # A valid old+new signed root carrying the full previous ledger
        # is likewise NOT permitted to have an active revoked key.
        new["revoked_key_ids"]=["builder1","builder2","root1"]
        with self.assertRaisesRegex(gate.TrustRejected,
                                    "Revoked signer cannot retain"):
            self.rotate(new,previous=previous)

    def test_12_P2_F43_02_expired_previous_root_cannot_authorize_rotation(self):
        """Port PR #45 test_16: previous policy was valid when loaded,
        becomes expired before rotation, new root has valid current expiry
        and both OLD+NEW threshold signatures. Must deny precisely on
        prior policy expiry rather than signature validity.
        """
        old=self.make_policy(expires_at=NOW+10)
        previous=self.auth_root(old,now=NOW)
        self.assertEqual(previous.expires_at,NOW+10)
        rotated=self.new_policy(issued_at=NOW+11,expires_at=NOW+600)
        with self.assertRaisesRegex(gate.TrustRejected,
                                    "Expired previous root"):
            self.rotate(rotated,previous=previous,now=NOW+11)

    def test_13_valid_rotated_builder_replacement_preserves_monotonic_revocation(self):
        old=self.make_policy(
            revoked=("builder1",),builder_ids=("builder2",))
        previous=self.auth_root(old)
        nextp=self.new_policy(
            revoked_key_ids=["builder1","root1"],
            role_keys={**self.initial["role_keys"],
                       "builder":self.root_map("builder2")})
        verified=self.rotate(nextp,previous=previous)
        self.assertIn("builder1",verified.revoked_key_ids)
        self.assertIn("builder2",verified.role_keys["builder"])
        with self.assertRaisesRegex(gate.TrustRejected,
                                    "Revoked"):
            self.check(self.bundle(verified,builder_signer="builder1"),
                       minimum_root_version=2)
        approved=self.check(self.bundle(verified,builder_signer="builder2"),
                            minimum_root_version=2)
        self.assertEqual(approved.root_version,2)

    def test_14_old_role_key_reuse_or_role_swap_blocked_even_if_signed(self):
        for p in (
            self.new_policy(role_keys={
                **self.initial["role_keys"],
                "source":self.root_map("source2"),
                "release":self.root_map("source1"),
            }),
            self.new_policy(root_keys={
                "root2":public_hex(self.keys["root1"]),
                "root3":public_hex(self.keys["root3"]),
                "root4":public_hex(self.keys["root4"]),
            }),
        ):
            with self.subTest(roles=p["role_keys"],roots=p["root_keys"]):
                with self.assertRaises(gate.TrustRejected):
                    self.rotate(p)

    def test_15_reuse_public_material_across_root_builder_release_denied(self):
        p=self.make_policy()
        p["role_keys"]={
            **p["role_keys"],
            "release":{"release1":public_hex(self.keys["root1"])},
        }
        with self.assertRaisesRegex(gate.TrustRejected,"independent"):
            self.auth_root(p)

    def test_16_unauthorized_source_builder_release_signer_role_confusion_denied(self):
        for changes in (
            {"source_signer":"builder1"},
            {"builder_signer":"release1"},
            {"release_signer":"source1"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(gate.TrustRejected,"not authorized"):
                    self.check(self.bundle(**changes))

    def test_17_fake_signature_with_authorized_key_id_rejected(self):
        payload=self.bundle()
        bad=dict(payload)
        bad["builder_signature"]=self.keys["attacker1"].sign(
            gate.BUILDER_DOMAIN+payload["builder_raw"]).hex()
        with self.assertRaisesRegex(gate.TrustRejected,"signature"):
            self.check(bad)
        bad=dict(payload)
        bad["release_signature"]=self.keys["attacker1"].sign(
            gate.RELEASE_DOMAIN+payload["release_raw"]).hex()
        with self.assertRaisesRegex(gate.TrustRejected,"signature"):
            self.check(bad)

    def test_18_wrong_source_repo_ref_commit_and_tree_rejected(self):
        for field,val in (("repo","github.com/attacker/flight"),
                          ("ref","refs/heads/attacker"),
                          ("commit","a"*40),("tree_sha256","0"*64)):
            with self.subTest(field=field):
                with self.assertRaises(gate.TrustRejected):
                    self.check(self.bundle(source_updates={field:val}))

    def test_19_builder_workflow_and_attestation_link_rejected(self):
        # Actual authorizer-pinned workflow and signed source reference
        # MUST fail closed. Recipe hashes are DIFFERENT: signed claims
        # without independently trusted expected recipe (positive test 29).
        for change in ({"builder_workflow":"github.com/attacker/build"},
                       {"source_attestation_sha256":"0"*64}):
            with self.subTest(change=change):
                with self.assertRaises(gate.TrustRejected):
                    self.check(self.bundle(builder_updates=change))

    def test_20_signed_release_cannot_disagree_with_source_build_chain(self):
        for updates in (
            {"builder_attestation_sha256":"0"*64},
            {"source_attestation_sha256":"0"*64},
            {"artifact_sha256":"0"*64},
            {"recipe_sha256":"0"*64},
            {"channel":"production"},
            {"platform":"windows"},
        ):
            with self.subTest(updates=updates):
                with self.assertRaises(gate.TrustRejected):
                    self.check(self.bundle(release_updates=updates))

    def test_21_actual_unsigned_foreign_bytes_and_length_rejected(self):
        b=self.bundle()
        for val in (b"OTHER ARTIFACT",CONTENT+b"MORE",b""):
            with self.subTest(data=val):
                with self.assertRaises(gate.TrustRejected):
                    self.check(b,artifact=val)

    def test_22_revocation_and_freshness_of_current_verified_root_enforced(self):
        expired=self.make_policy(expires_at=NOW-1)
        with self.assertRaises(gate.TrustRejected):
            self.auth_root(expired,now=NOW)
        revoked=self.make_policy(
            revoked=("builder1",),builder_ids=("builder2",))
        checked=self.auth_root(revoked)
        with self.assertRaisesRegex(gate.TrustRejected,"Revoked"):
            self.check(self.bundle(checked,builder_signer="builder1"))

    def test_23_signed_root_and_sequence_caller_floor_enforced(self):
        with self.assertRaisesRegex(gate.TrustRejected,"rollback"):
            self.auth_root(self.initial,minimum=2)
        with self.assertRaises(gate.TrustRejected):
            self.check(self.bundle(),minimum_sequence=10)
        with self.assertRaisesRegex(gate.TrustRejected,"rollback"):
            self.check(self.bundle(),minimum_root_version=2)

    def test_24_POSITIVE_LIMIT_attacker_controls_roster_and_pin_authenticity(self):
        """Preexisting P1: caller can self-pin if attacker controls both
        bytes and asserted authenticated digest. NOT real OOB trust.
        """
        fake=self.root_map("attacker1","attacker2","attacker3")
        fake_pin=gate.pin_bootstrap_roots(fake,2,gate.pin_digest(fake,2))
        p=self.make_policy(root_ids=("attacker1","attacker2","attacker3"))
        accepted=self.auth_root(p,signers=("attacker1","attacker2"),
                                bootstrap=fake_pin)
        self.assertEqual(set(accepted.root_keys),set(fake))
        self.assertNotEqual(dict(self.pins.keys),dict(fake_pin.keys))

    def test_25_POSITIVE_LIMIT_authorized_signers_can_assert_fictitious_build(self):
        """A valid signed source/build/release chain can lie in *all*
        fields consistently. No real-source CI attestation exists here.
        """
        fakecommit="a"*40
        tree="b"*64
        data=self.bundle(
            source_updates={"commit":fakecommit,"tree_sha256":tree})
        verified=self.check(data,expected_commit=fakecommit,
                            expected_tree_sha256=tree)
        self.assertEqual(verified.source_commit,fakecommit)

    def test_26_POSITIVE_LIMIT_stale_caller_sequence_allows_replay(self):
        payload=self.bundle()
        a=self.check(payload)
        b=self.check(payload)
        self.assertEqual(a,b)

    def test_27_public_fabrication_of_verified_root_or_provenance_denied(self):
        with self.assertRaisesRegex(gate.TrustRejected,"threshold"):
            gate.RootAuthority(version=1)
        with self.assertRaisesRegex(gate.TrustRejected,"chain"):
            gate.VerifiedProvenance(root_version=1)

    def test_28_CI_ephemeral_key_and_original_attack_witnesses_preserved(self):
        p=Path(__file__).with_name("flight_pr41_independent_security_qa.py")
        self.assertTrue(p.is_file())
        old=Path(__file__).with_name("flight_p1_root_provenance_ci_tests.py")
        text=old.read_text(encoding="utf-8")
        for i in range(1,35):
            self.assertIn(f"def test_{i:02d}_",text)
        self.assertIn("test_31_positive_limit_unadvanced_floor",text)
        self.assertIn("test_32_positive_limit_forged_self_pin",text)
        self.assertFalse(any(
            "PRIVATE KEY" in json.dumps(x) for x in
            (self.initial,self.new_policy())))
        self.assertNotEqual(
            self.keys["root1"].private_bytes_raw(),
            self.keys["root2"].private_bytes_raw())


    def test_29_POSITIVE_LIMIT_signed_recipe_materials_are_not_independent_provenance(self):
        """Authorized test builder and release signers can agree on a FALSE
        recipe/materials SHA. Those digests are signed and linked but the
        verifier has no independently reviewed expected recipe/materials.
        This tests the P1 'real provenance' blocker; NOT a P2 cryptobypass.
        """
        b=self.bundle(builder_updates={
            "recipe_sha256":"0"*64,
            "materials_sha256":"1"*64,
        })
        accepted=self.check(b)
        self.assertEqual(accepted.source_commit,COMMIT)
        self.assertEqual(accepted.artifact_sha256,hashlib.sha256(CONTENT).hexdigest())
        signed_builder=json.loads(b["builder_raw"])
        signed_release=json.loads(b["release_raw"])
        self.assertEqual(signed_builder["recipe_sha256"],"0"*64)
        self.assertEqual(signed_release["recipe_sha256"],"0"*64)
        self.assertEqual(signed_builder["materials_sha256"],"1"*64)
        self.assertEqual(signed_release["materials_sha256"],"1"*64)


if __name__=="__main__":
    unittest.main(verbosity=2)
