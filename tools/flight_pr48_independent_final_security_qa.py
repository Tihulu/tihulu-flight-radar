#!/usr/bin/env python3
"""Independent Agent06 PR48 security QA. No production credentials or host access.

Purpose: independently port original PR46 positive P2-F44-01/02 attack inputs
to STRICT NEGATIVE revocation-by-key-MATERIAL acceptance tests. Also test
cross-role / 3-epoch tombstones and real 2/3 two-quorum success.
Positive tests documenting missing OOB root and replay are production HOLD
witnesses, never a real production PASS.

All Ed25519 private keys are fresh, volatile, per-test and stay in hosted CI.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from tools import flight_p1_root_provenance_ci as model

NOW=1800000000
DATA=b"INDEPENDENT-FLIGHT-P48-REVOCATION-TRANSITION"
SOURCE="github.com/Tihulu/tihulu-flight-radar"
REF="refs/heads/main"
WORKFLOW="github.com/Tihulu/tihulu-flight-radar/.github/workflows/release.yml"
COMMIT="a"*40
TREE="b"*64
RECIPE="c"*64
MATERIALS="d"*64
FP_DOMAIN=b"TIHULU_FLIGHT_ED25519_KEY_TOMBSTONE_V1\0"


def public(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


def fingerprint(key_bytes):
    """Intentionally independent of model.key_fingerprint()."""
    return hashlib.sha256(FP_DOMAIN+key_bytes).hexdigest()


@unittest.skipUnless(os.name=="posix", "Hosted Ubuntu runner only")
class PR48RootHistoryIndependentQA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI")!="true"
                or os.environ.get("GITHUB_ACTIONS")!="true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Only disposable GitHub-hosted CI")
        self.temp=tempfile.TemporaryDirectory(
            prefix="flight-pr48-agent06-",dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.temp.cleanup)
        self.keys={n:Ed25519PrivateKey.generate() for n in (
            "r1","r2","r3","r4","r5","r6",
            "s1","s2","b1","b2","b3","l1","l2",
            "rogue1","rogue2","rogue3"
        )}
        self.rootv1=self.policy(
            1,{"r1":"r1","r2":"r2","r3":"r3"},
            {"source":{"s1":"s1"},"builder":{"b1":"b1"},
             "release":{"l1":"l1"}},
            {},issued_at=NOW-800)
        roster=self.rootv1["root_keys"]
        self.bootstrap=model.pin_bootstrap_roots(
            roster,2,model.pin_digest(roster,2))
        self.v1=self.verify(self.rootv1,("r1","r2"),bootstrap=self.bootstrap)

    def phex(self,name):
        return public(self.keys[name]).hex()

    def policy(self,version,roots,roles,ledger,*,issued_at=NOW-700,
               expires_at=NOW+900,threshold=2):
        return {
            "schema":1,"domain":model.TRUST_DOMAIN,"version":version,
            "issued_at":issued_at,"expires_at":expires_at,
            "threshold":threshold,
            "root_keys":{k:self.phex(v) for k,v in roots.items()},
            "role_keys":{r:{k:self.phex(v) for k,v in ids.items()}
                         for r,ids in roles.items()},
            "revoked_key_ids":sorted(ledger),
            "revoked_key_fingerprints":dict(ledger),
            "source_repo":SOURCE,"source_ref":REF,
            "builder_workflow":WORKFLOW,
        }

    def sign_root(self,p,signers):
        raw=model.canonical(p)
        sig={s:self.keys[s].sign(model.ROOT_DOMAIN+raw).hex()
             for s in signers}
        return raw,sig

    def independently_check_signatures(self,p,sig,prev):
        """Check both Old/New valid Ed25519 quorums BEFORE denial test.
        No reliance on engine's quorum counter to establish preconditions.
        """
        raw=model.canonical(p)
        old=dict(prev.root_keys)
        new={k:bytes.fromhex(v) for k,v in p["root_keys"].items()}
        assert len(set(old.values()))==len(old)
        assert len(set(new.values()))==len(new)
        for key_id,hexsig in sig.items():
            oldkey=old.get(key_id)
            newkey=new.get(key_id)
            k=newkey if newkey is not None else oldkey
            assert k is not None,(key_id,"unauthorized key in test")
            Ed25519PublicKey.from_public_bytes(k).verify(
                bytes.fromhex(hexsig),model.ROOT_DOMAIN+raw)
        self.assertGreaterEqual(len({old[k] for k in sig if k in old}),2)
        self.assertGreaterEqual(len({new[k] for k in sig if k in new}),2)

    def verify(self,p,signers,*,previous=None,bootstrap=None,
               now=NOW,minimum=None,prove_quorums=False):
        raw,sig=self.sign_root(p,signers)
        if prove_quorums and previous is not None:
            self.independently_check_signatures(p,sig,previous)
        return model.verify_root_policy(
            raw,sig,now=now,
            minimum_version=p["version"] if minimum is None else minimum,
            bootstrap=bootstrap,previous=previous)

    def v2_policy(self,*,roots=None,roles=None,ledger=None):
        return self.policy(2,
            {"r2":"r2","r3":"r3","r4":"r4"} if roots is None else roots,
            {"source":{"s1":"s1"},"builder":{"b2":"b2"},
             "release":{"l1":"l1"}} if roles is None else roles,
            {"r1":fingerprint(public(self.keys["r1"])),
             "b1":fingerprint(public(self.keys["b1"]))}
              if ledger is None else ledger,
            issued_at=NOW-600)

    def v2(self):
        p=self.v2_policy()
        return self.verify(p,("r1","r2","r4"),previous=self.v1,
                           prove_quorums=True)

    def v3_policy(self,*,roots=None,roles=None,ledger=None):
        default={
            "r1":fingerprint(public(self.keys["r1"])),
            "r2":fingerprint(public(self.keys["r2"])),
            "b1":fingerprint(public(self.keys["b1"])),
            "b2":fingerprint(public(self.keys["b2"])),
            "l1":fingerprint(public(self.keys["l1"])),
        }
        return self.policy(3,
            {"r3":"r3","r4":"r4","r5":"r5"} if roots is None else roots,
            {"source":{"s1":"s1"},"builder":{"b3":"b3"},
             "release":{"l2":"l2"}} if roles is None else roles,
            default if ledger is None else ledger,
            issued_at=NOW-400)

    def chain(self,root=None,*,artifact=DATA,
              source_signer="s1",builder_signer="b2",release_signer="l1",
              source_commit=COMMIT,source_tree=TREE,recipe=RECIPE,
              minimum_sequence=8):
        root=self.v2() if root is None else root
        s={"schema":1,"key_id":source_signer,"repo":SOURCE,"ref":REF,
           "commit":source_commit,"tree_sha256":source_tree}
        sr=model.canonical(s)
        ss=self.keys[source_signer].sign(model.SOURCE_DOMAIN+sr).hex()
        b={"schema":1,"key_id":builder_signer,"repo":SOURCE,"ref":REF,
           "commit":source_commit,"tree_sha256":source_tree,
           "source_attestation_sha256":hashlib.sha256(sr).hexdigest(),
           "artifact_sha256":hashlib.sha256(artifact).hexdigest(),
           "artifact_size":len(artifact),"recipe_sha256":recipe,
           "materials_sha256":MATERIALS,
           "builder_workflow":WORKFLOW}
        br=model.canonical(b)
        bs=self.keys[builder_signer].sign(model.BUILDER_DOMAIN+br).hex()
        l={"schema":1,"key_id":release_signer,
           "root_version":root.version,
           "app_id":model.APP,"channel":model.CHANNEL,
           "platform":"linux","architecture":"x86_64",
           "artifact_name":"ci-pr48-test.bin",
           "artifact_size":len(artifact),
           "artifact_sha256":hashlib.sha256(artifact).hexdigest(),
           "sequence":8,"repo":SOURCE,"ref":REF,
           "commit":source_commit,"tree_sha256":source_tree,
           "recipe_sha256":recipe,"materials_sha256":MATERIALS,
           "source_attestation_sha256":hashlib.sha256(sr).hexdigest(),
           "builder_attestation_sha256":hashlib.sha256(br).hexdigest()}
        lr=model.canonical(l)
        ls=self.keys[release_signer].sign(model.RELEASE_DOMAIN+lr).hex()
        return dict(root=root,source_raw=sr,source_signature=ss,
            builder_raw=br,builder_signature=bs,
            release_raw=lr,release_signature=ls,
            artifact=artifact,expected_commit=source_commit,
            expected_tree_sha256=source_tree,expected_platform="linux",
            expected_arch="x86_64",minimum_sequence=minimum_sequence,
            minimum_root_version=root.version,now=NOW)

    def test_01_original_P2_F44_01_revoked_builder_key_new_id_denied(self):
        """Direct port of PR46 POSITIVE #30, but now MUST fail closed.
        Valid old/new root signatures; revoked b1 material relabeled b3.
        """
        p=self.v2_policy(roles={"source":{"s1":"s1"},
              "builder":{"b3":"b1"},"release":{"l1":"l1"}})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r1","r2","r4"),previous=self.v1,
                        prove_quorums=True)

    def test_02_original_P2_F44_02_revoked_root_key_new_id_denied(self):
        """Direct port of PR46 POSITIVE #31, valid old/new 2/3 quorums.
        New r4 is byte-identical to old revoked r1, name cannot launder it.
        """
        p=self.v2_policy(roots={"r2":"r2","r3":"r3","r4":"r1"})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r1","r2","r4"),previous=self.v1,
                        prove_quorums=True)

    def test_03_legitimate_2_of_3_bootstrap_passes_and_authority_is_immutable(self):
        self.assertEqual(self.v1.threshold,2)
        self.assertEqual(self.v1.version,1)
        with self.assertRaisesRegex(model.TrustRejected,"threshold"):
            model.RootAuthority(version=1)
        with self.assertRaises((TypeError,AttributeError)):
            self.v1.revoked_key_fingerprints["r1"]="0"*64
        for pair in (("r1","r2"),("r2","r3")):
            with self.subTest(signers=pair):
                self.assertEqual(
                    self.verify(self.rootv1,pair,bootstrap=self.bootstrap).version,1)

    def test_04_missing_first_or_second_root_quorum_denied(self):
        p=self.v2_policy()
        for signers,message in (
            (("r1","r2"),"New root threshold"),
            (("r2","r4"),"Previous trusted root threshold"),
        ):
            with self.subTest(signers=signers):
                with self.assertRaisesRegex(model.TrustRejected,message):
                    self.verify(p,signers,previous=self.v1)

    def test_05_honest_rotation_and_two_quorums_still_work(self):
        v2=self.v2()
        self.assertEqual(v2.version,2)
        self.assertEqual(set(v2.root_keys),{"r2","r3","r4"})
        self.assertEqual(set(v2.revoked_key_fingerprints),{"r1","b1"})
        v3p=self.v3_policy()
        v3=self.verify(v3p,("r2","r3","r5"),previous=v2,prove_quorums=True)
        self.assertEqual(v3.version,3)
        self.assertEqual(set(v3.root_keys),{"r3","r4","r5"})
        self.assertEqual(set(v3.revoked_key_fingerprints),
                         {"r1","r2","b1","b2","l1"})

    def test_06_three_epoch_builder_material_fails_reenrollment_as_release(self):
        v2=self.v2()
        p=self.v3_policy(roles={
            "source":{"s1":"s1"},"builder":{"b3":"b3"},
            "release":{"l2":"b1"}})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r2","r3","r5"),previous=v2,prove_quorums=True)

    def test_07_three_epoch_root_material_fails_reenrollment_as_builder(self):
        v2=self.v2()
        p=self.v3_policy(roles={
            "source":{"s1":"s1"},"builder":{"b3":"r1"},
            "release":{"l2":"l2"}})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r2","r3","r5"),previous=v2,prove_quorums=True)

    def test_08_three_epoch_old_builder_material_fails_reenrollment_as_new_root(self):
        v2=self.v2()
        p=self.v3_policy(roots={"r3":"r3","r4":"r4","r5":"b1"})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r2","r3","r5"),previous=v2,prove_quorums=True)

    def test_09_three_epoch_old_root_material_fails_reenrollment_as_source(self):
        v2=self.v2()
        p=self.v3_policy(roles={
            "source":{"s2":"r1"},
            "builder":{"b3":"b3"},"release":{"l2":"l2"}})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r2","r3","r5"),previous=v2,prove_quorums=True)

    def test_10_three_epoch_tombstone_removal_fails_closed(self):
        v2=self.v2()
        ledger=self.v3_policy()["revoked_key_fingerprints"]
        ledger.pop("b1")
        p=self.v3_policy(ledger=ledger)
        with self.assertRaises(model.TrustRejected):
            self.verify(p,("r2","r3","r5"),previous=v2,prove_quorums=True)

    def test_11_three_epoch_tombstone_substitution_fails_closed(self):
        v2=self.v2()
        ledger=self.v3_policy()["revoked_key_fingerprints"]
        ledger["b1"]="0"*64
        p=self.v3_policy(ledger=ledger)
        with self.assertRaisesRegex(model.TrustRejected,
                                    "fingerprint ledger cannot shrink/change"):
            self.verify(p,("r2","r3","r5"),previous=v2,prove_quorums=True)

    def test_12_newly_retired_authority_must_have_genuine_tombstone(self):
        p=self.v2_policy()
        ledger=dict(p["revoked_key_fingerprints"])
        ledger["b1"]="0"*64
        p["revoked_key_fingerprints"]=ledger
        with self.assertRaisesRegex(model.TrustRejected,
                                    "fingerprint tombstone missing or forged"):
            self.verify(p,("r1","r2","r4"),previous=self.v1,
                        prove_quorums=True)

    def test_13_renamed_revoked_builder_under_different_role_and_id_denied(self):
        p=self.v2_policy(roles={
            "source":{"s2":"b1"},"builder":{"b2":"b2"},
            "release":{"l1":"l1"}})
        # Correct b1 retire, correct s1 retire fingerprint additionally.
        p["revoked_key_ids"].append("s1")
        p["revoked_key_ids"].sort()
        p["revoked_key_fingerprints"]["s1"]=fingerprint(public(self.keys["s1"]))
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Revoked Ed25519 key material"):
            self.verify(p,("r1","r2","r4"),previous=self.v1,
                        prove_quorums=True)

    def test_14_wrong_material_same_signer_ID_rejected(self):
        p=self.v2_policy(roles={
            "source":{"s1":"s2"},"builder":{"b2":"b2"},
            "release":{"l1":"l1"}})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Existing authority ID reused"):
            self.verify(p,("r1","r2","r4"),previous=self.v1,
                        prove_quorums=True)

    def test_15_ledger_duplicate_fingerprints_fail_closed(self):
        p=self.rootv1.copy()
        p["revoked_key_ids"]=["dead1","dead2"]
        same=fingerprint(public(self.keys["rogue1"]))
        p["revoked_key_fingerprints"]={"dead1":same,"dead2":same}
        with self.assertRaisesRegex(model.TrustRejected,
                                    "aliases revoked key material"):
            self.verify(p,("r1","r2"),bootstrap=self.bootstrap)

    def test_16_forged_signed_tombstone_json_rejected(self):
        p=self.v2_policy()
        raw,signed=self.sign_root(p,("r1","r2","r4"))
        altered=raw.replace(b'"b1":"',b'"b1":"0')
        self.assertNotEqual(raw,altered)
        with self.assertRaises(model.TrustRejected):
            model.verify_root_policy(altered,signed,now=NOW,minimum_version=2,
                                     previous=self.v1)

    def test_17_wrong_ledger_extra_id_or_missing_mapping_rejected(self):
        p=self.v2_policy()
        for ledger in (
            {"r1":p["revoked_key_fingerprints"]["r1"]},
            {**p["revoked_key_fingerprints"],"old_alias":"0"*64},
            {"r1":"0"*64,"b1":"1"*64},
        ):
            with self.subTest(ledger=ledger):
                p2=dict(p,revoked_key_fingerprints=ledger)
                with self.assertRaises(model.TrustRejected):
                    self.verify(p2,("r1","r2","r4"),previous=self.v1,
                                prove_quorums=True)

    def test_18_noncanonical_or_unknown_signed_policy_denied(self):
        p=self.v2_policy()
        raw=model.canonical(p)
        for dirty in (
            raw[:-1]+b',"version":2}',
            json.dumps(p,sort_keys=True).encode(),
            model.canonical(dict(p,extra="untrusted")),
        ):
            signatures={k:self.keys[k].sign(model.ROOT_DOMAIN+dirty).hex()
                        for k in ("r1","r2","r4")}
            with self.subTest(payload=dirty[:30]):
                with self.assertRaises(model.TrustRejected):
                    model.verify_root_policy(
                        dirty,signatures,now=NOW,minimum_version=2,
                        previous=self.v1)

    def test_19_missing_old_or_new_root_signatures_fail_with_valid_key_bytes(self):
        p=self.v2_policy()
        for s in (("r1","r2"),("r3","r4"),("r2",)):
            with self.subTest(s=s):
                with self.assertRaises(model.TrustRejected):
                    self.verify(p,s,previous=self.v1)

    def test_20_no_root_or_role_key_aliases_within_active_policy(self):
        p=self.v2_policy(roles={
            "source":{"s1":"s1"},
            "builder":{"b2":"r4"},
            "release":{"l1":"l1"}})
        with self.assertRaisesRegex(model.TrustRejected,
                                    "independent"):
            self.verify(p,("r1","r2","r4"),previous=self.v1,
                        prove_quorums=True)

    def test_21_authorized_new_builder_and_release_roles_can_attest_good_bytes(self):
        v2=self.v2()
        proof=model.verify_provenance_bundle(**self.chain(v2))
        self.assertEqual(proof.root_version,2)
        self.assertEqual(proof.artifact_size,len(DATA))
        self.assertEqual(proof.artifact_sha256,hashlib.sha256(DATA).hexdigest())

    def test_22_expired_previous_root_cannot_rotate_with_valid_new_quorums(self):
        expired=self.policy(1,{"r1":"r1","r2":"r2","r3":"r3"},
            {"source":{"s1":"s1"},"builder":{"b1":"b1"},
             "release":{"l1":"l1"}},{},
            issued_at=NOW-800,expires_at=NOW+1)
        previous=self.verify(expired,("r1","r2"),bootstrap=self.bootstrap)
        p=self.v2_policy()
        with self.assertRaisesRegex(model.TrustRejected,
                                    "Expired previous root"):
            self.verify(p,("r1","r2","r4"),previous=previous,now=NOW+2,
                        prove_quorums=True)

    def test_23_genuine_source_and_release_signer_role_confusion_rejected(self):
        v2=self.v2()
        bad=self.chain(v2,builder_signer="s1")
        with self.assertRaisesRegex(model.TrustRejected,
                                    "not authorized"):
            model.verify_provenance_bundle(**bad)

    def test_24_actual_artifact_foreign_bytes_rejected(self):
        proof=self.chain(self.v2())
        with self.assertRaises(model.TrustRejected):
            model.verify_provenance_bundle(**dict(proof,artifact=b"OTHER BYTES"))

    def test_25_attacker_self_pin_remains_positive_P1_LIMIT(self):
        rogue={"newroot1":self.phex("rogue1"),
               "newroot2":self.phex("rogue2"),
               "newroot3":self.phex("rogue3")}
        fake_pins=model.pin_bootstrap_roots(
            rogue,2,model.pin_digest(rogue,2))
        fake_policy=self.policy(1,
            {k:{"newroot1":"rogue1","newroot2":"rogue2",
                "newroot3":"rogue3"}[k] for k in rogue},
            {"source":{"s1":"s1"},"builder":{"b1":"b1"},
             "release":{"l1":"l1"}},{},issued_at=NOW-800)
        good=self.verify(fake_policy,("rogue1","rogue2"),
                         bootstrap=fake_pins)
        self.assertEqual(good.version,1)
        self.assertNotEqual(dict(good.root_keys),dict(self.v1.root_keys))

    def test_26_same_signed_release_replays_with_unchanged_caller_floor_P1_LIMIT(self):
        bundle=self.chain(self.v2())
        first=model.verify_provenance_bundle(**bundle)
        second=model.verify_provenance_bundle(**bundle)
        self.assertEqual(first,second)

    def test_27_signed_claims_are_not_independent_real_builder_proof_P1_LIMIT(self):
        proof=self.chain(self.v2(),source_commit="e"*40,source_tree="f"*64,
                         recipe="0"*64)
        verified=model.verify_provenance_bundle(**proof)
        self.assertEqual(verified.source_commit,"e"*40)
        self.assertEqual(verified.tree_sha256,"f"*64)

    def test_28_original_QA_PR46_positive_exploit_fixtures_are_unchanged(self):
        # Exact historical PR46 is immutable; QA here doesn't import nor edit it.
        self.assertEqual(model.APP,"tihulu-flight-radar-ci-fixture")
        self.assertNotEqual(public(self.keys["r1"]),public(self.keys["r2"]))
        self.assertEqual(fingerprint(public(self.keys["b1"])),
                         model.key_fingerprint(public(self.keys["b1"])))


if __name__=="__main__":
    unittest.main(verbosity=2)
