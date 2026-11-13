#!/usr/bin/env python3
"""Agent 07 P1-ROOT/PROVENANCE disposable Linux CI-only negative tests.

Ephemeral Ed25519 private signing keys are created only in RAM per test.
Public pin *fingerprints* in this suite are deliberately synthetic and do
NOT create a real authenticated production root or trusted release.

The tests that demonstrate untrusted caller policy (self-pinning/clock/replay)
pass by POSITIVELY reproducing an out-of-scope trust weakness.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import flight_p1_root_provenance_ci as gate

NOW = 1800000000
ARTIFACT = b"DISPOSABLE-FLIGHT-ROOT-ATTESTED-PAYLOAD"
REPO = "github.com/Tihulu/tihulu-flight-radar"
REF = "refs/heads/main"
WORKFLOW = "github.com/Tihulu/tihulu-flight-radar/.github/workflows/release.yml"
COMMIT = "a" * 40
TREE = "b" * 64
RECIPE = "c" * 64
MATERIALS = "d" * 64


@unittest.skipUnless(os.name == "posix", "Linux hosted CI only")
class P1RootProvenanceCI(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI") != "true"
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Only disposable GitHub-hosted CI tests")
        self.tmp = tempfile.TemporaryDirectory(
            prefix="flight-p1-root-provenance-", dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.test_root = Path(self.tmp.name)
        self.keys = {}
        for identifier in ("root1", "root2", "root3", "source1",
                           "builder1", "release1"):
            self.keys[identifier] = Ed25519PrivateKey.generate()
        self.root_keys = self.public_map("root1", "root2", "root3")
        self.role_keys = {
            "source": self.public_map("source1"),
            "builder": self.public_map("builder1"),
            "release": self.public_map("release1"),
        }
        self.root_policy = {
            "schema": 1, "domain": gate.TRUST_DOMAIN,
            "version": 1, "threshold": 2,
            "issued_at": NOW-1000, "expires_at": NOW+1000,
            "root_keys": dict(self.root_keys),
            "role_keys": {r: dict(v) for r, v in self.role_keys.items()},
            "revoked_key_ids": [], "source_repo": REPO,
            "source_ref": REF, "builder_workflow": WORKFLOW,
        }
        self.pins = gate.pin_bootstrap_roots(
            self.root_keys, 2, gate.pin_digest(self.root_keys, 2))
        self.root = self.authenticate_root()

    def public_map(self, *ids):
        return {
            id_: self.keys[id_].public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw).hex()
            for id_ in ids
        }

    def signed_policy(self, policy=None, endorsers=None):
        raw = gate.canonical(self.root_policy if policy is None else policy)
        if endorsers is None:
            endorsers = ("root1", "root2")
        signatures = {
            key_id: self.keys[key_id].sign(gate.ROOT_DOMAIN+raw).hex()
            for key_id in endorsers
        }
        return raw, signatures

    def authenticate_root(self, policy=None, endorsers=None, *,
                          previous=None, pins=None, minimum=1, now=NOW):
        raw, signatures = self.signed_policy(policy, endorsers)
        return gate.verify_root_policy(
            raw, signatures, now=now, minimum_version=minimum,
            bootstrap=(self.pins if pins is None else pins)
            if previous is None else None,
            previous=previous,
        )

    def signed_bundle(self, root=None, *, source_mod=None, build_mod=None,
                      release_mod=None, source_signer="source1",
                      builder_signer="builder1", release_signer="release1",
                      artifact=ARTIFACT):
        root = self.root if root is None else root
        source = {
            "schema": 1, "key_id": source_signer, "repo": REPO, "ref": REF,
            "commit": COMMIT, "tree_sha256": TREE,
        }
        if source_mod:
            source.update(source_mod)
        source_raw = gate.canonical(source)
        source_sig = self.keys[source_signer].sign(gate.SOURCE_DOMAIN+source_raw).hex()
        builder = {
            **source, "key_id": builder_signer,
            "builder_workflow": WORKFLOW,
            "source_attestation_sha256": hashlib.sha256(source_raw).hexdigest(),
            "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
            "artifact_size": len(artifact), "recipe_sha256": RECIPE,
            "materials_sha256": MATERIALS,
        }
        if build_mod:
            builder.update(build_mod)
        build_raw = gate.canonical(builder)
        build_sig = self.keys[builder_signer].sign(gate.BUILDER_DOMAIN+build_raw).hex()
        release = {
            **{k: builder[k] for k in (
                "repo", "ref", "commit", "tree_sha256",
                "recipe_sha256", "materials_sha256",
                "artifact_sha256", "artifact_size",
                "source_attestation_sha256",
            )},
            "schema": 1, "key_id": release_signer,
            "root_version": root.version, "app_id": gate.APP,
            "channel": gate.CHANNEL, "platform": "linux",
            "architecture": "x86_64",
            "artifact_name": "ephemeral-ci-fixture.bin",
            "sequence": 8,
            "builder_attestation_sha256": hashlib.sha256(build_raw).hexdigest(),
        }
        if release_mod:
            release.update(release_mod)
        release_raw = gate.canonical(release)
        release_sig = self.keys[release_signer].sign(
            gate.RELEASE_DOMAIN+release_raw).hex()
        return {
            "root": root, "source_raw": source_raw,
            "source_signature": source_sig,
            "builder_raw": build_raw, "builder_signature": build_sig,
            "release_raw": release_raw, "release_signature": release_sig,
            "artifact": artifact,
            "expected_commit": COMMIT, "expected_tree_sha256": TREE,
            "expected_platform": "linux", "expected_arch": "x86_64",
            "minimum_sequence": 8, "minimum_root_version": root.version,
            "now": NOW,
        }

    def verify(self, bundle=None, **changes):
        payload = self.signed_bundle() if bundle is None else dict(bundle)
        payload.update(changes)
        return gate.verify_provenance_bundle(**payload)

    def rotated_policy(self):
        self.keys["root4"] = Ed25519PrivateKey.generate()
        self.keys["release2"] = Ed25519PrivateKey.generate()
        policy = {
            **self.root_policy, "version": 2,
            "issued_at": NOW-500,
            "root_keys": self.public_map("root2", "root3", "root4"),
            "role_keys": {
                **self.role_keys, "release": self.public_map("release2"),
            },
            "revoked_key_ids": ["release1", "root1"],
        }
        return policy

    def test_01_legitimate_2_of_3_pinned_root_and_three_role_provenance(self):
        self.assertEqual(self.root.version, 1)
        self.assertEqual(self.root.threshold, 2)
        result = self.verify()
        self.assertEqual(result.artifact_size, len(ARTIFACT))
        self.assertEqual(result.artifact_sha256, hashlib.sha256(ARTIFACT).hexdigest())
        self.assertEqual(result.source_commit, COMMIT)
        self.assertEqual(result.tree_sha256, TREE)
        self.assertEqual(result.root_version, 1)
        self.assertEqual(result.release_sequence, 8)

    def test_02_pin_fingerprint_must_match_out_of_band_material(self):
        with self.assertRaisesRegex(gate.TrustRejected, "differs"):
            gate.pin_bootstrap_roots(self.root_keys, 2, "0"*64)
        rogue = dict(self.root_keys)
        self.keys["attacker_root"] = Ed25519PrivateKey.generate()
        rogue["root1"] = self.public_map("attacker_root")["attacker_root"]
        with self.assertRaisesRegex(gate.TrustRejected, "differs"):
            gate.pin_bootstrap_roots(rogue, 2, self.pins.pin_sha256)

    def test_03_unsigned_or_incompletely_endorsed_initial_roots_denied(self):
        for endorsers in ((), ("root1",), ("source1",)):
            with self.subTest(endorsers=endorsers):
                with self.assertRaises(gate.TrustRejected):
                    self.authenticate_root(endorsers=endorsers)

    def test_04_valid_signer_but_tampered_root_bytes_denied(self):
        raw, signatures = self.signed_policy()
        altered = raw.replace(b'"version":1', b'"version":2')
        self.assertNotEqual(raw, altered)
        with self.assertRaises(gate.TrustRejected):
            gate.verify_root_policy(altered, signatures, now=NOW,
                minimum_version=1, bootstrap=self.pins)

    def test_05_noncanonical_duplicate_or_unknown_root_fields_denied(self):
        raw, sig = self.signed_policy()
        duplicate = raw[:-1]+b',"schema":1}'
        new_sig = {k: self.keys[k].sign(gate.ROOT_DOMAIN+duplicate).hex()
                   for k in ("root1", "root2")}
        with self.assertRaisesRegex(gate.TrustRejected, "Duplicate"):
            gate.verify_root_policy(duplicate, new_sig, now=NOW,
                minimum_version=1, bootstrap=self.pins)
        with self.assertRaises(gate.TrustRejected):
            self.authenticate_root({**self.root_policy,"extra":{"keys":["x"]}})
        spaced = json.dumps(self.root_policy, sort_keys=True).encode()
        sigs = {k:self.keys[k].sign(gate.ROOT_DOMAIN+spaced).hex()
                for k in ("root1","root2")}
        with self.assertRaisesRegex(gate.TrustRejected,"Noncanonical"):
            gate.verify_root_policy(spaced,sigs,now=NOW,
                                    minimum_version=1,bootstrap=self.pins)

    def test_06_production_root_object_cannot_be_publicly_fabricated(self):
        with self.assertRaisesRegex(gate.TrustRejected,"threshold"):
            gate.RootAuthority(version=1, root_keys=self.root_keys)
        with self.assertRaisesRegex(gate.TrustRejected,"source/builder/release"):
            gate.VerifiedProvenance(root_version=1)
        with self.assertRaises((TypeError, AttributeError)):
            self.root.root_keys["root1"] = b"BAD"

    def test_07_initial_roster_must_match_pins_exactly(self):
        alternate = {**self.root_policy,
                     "root_keys":self.public_map("root1","root2")}
        with self.assertRaises(gate.TrustRejected):
            self.authenticate_root(alternate, endorsers=("root1","root2"))

    def test_08_root_key_role_overlap_and_duplicate_public_key_denied(self):
        malicious = {
            **self.root_policy, "role_keys": {
                **self.role_keys, "release": {"root1":self.root_keys["root1"]},
            }
        }
        with self.assertRaisesRegex(gate.TrustRejected,"independent"):
            self.authenticate_root(malicious)
        equalbytes = {**self.root_policy,
                      "root_keys": {**self.root_keys,"root3":self.root_keys["root1"]}}
        with self.assertRaises(gate.TrustRejected):
            self.authenticate_root(equalbytes)

    def test_09_successful_rotation_requires_old_and_new_root_quorum(self):
        next_policy = self.rotated_policy()
        rotated = self.authenticate_root(
            next_policy, ("root1","root2","root4"), previous=self.root, minimum=2)
        self.assertEqual(rotated.version,2)
        self.assertEqual(set(rotated.root_keys),{"root2","root3","root4"})
        self.assertEqual(set(rotated.role_keys["release"]),{"release2"})
        self.assertEqual(rotated.revoked_key_ids,frozenset({"release1","root1"}))
        result = self.verify(self.signed_bundle(rotated,release_signer="release2"))
        self.assertEqual(result.root_version,2)

    def test_10_rotation_old_quorum_without_new_quorum_denied(self):
        policy = self.rotated_policy()
        with self.assertRaisesRegex(gate.TrustRejected,"New root threshold"):
            self.authenticate_root(policy,("root1","root2"),
                                   previous=self.root,minimum=2)

    def test_11_rotation_new_quorum_without_old_quorum_denied(self):
        policy = self.rotated_policy()
        with self.assertRaisesRegex(gate.TrustRejected,"Previous trusted root threshold"):
            self.authenticate_root(policy,("root3","root4"),
                                   previous=self.root,minimum=2)

    def test_12_rotation_requires_explicit_revocation_of_removed_keys(self):
        policy=self.rotated_policy()
        policy["revoked_key_ids"]=["root1"]
        with self.assertRaisesRegex(gate.TrustRejected,"Retired"):
            self.authenticate_root(policy,("root1","root2","root4"),
                                   previous=self.root,minimum=2)

    def test_13_reusing_existing_key_id_with_changed_public_key_denied(self):
        policy=self.rotated_policy()
        policy["root_keys"]["root2"] = self.root_keys["root1"]
        with self.assertRaises(gate.TrustRejected):
            self.authenticate_root(policy,("root1","root2","root4"),
                                   previous=self.root,minimum=2)

    def test_14_rotation_version_replay_or_skip_denied(self):
        policy=self.rotated_policy()
        policy["version"]=1
        with self.assertRaisesRegex(gate.TrustRejected,"exactly one"):
            self.authenticate_root(policy,("root1","root2","root4"),
                                   previous=self.root,minimum=1)
        policy["version"]=3
        with self.assertRaisesRegex(gate.TrustRejected,"exactly one"):
            self.authenticate_root(policy,("root1","root2","root4"),
                                   previous=self.root,minimum=3)

    def test_15_old_revoked_release_key_cannot_sign_after_rotation(self):
        policy=self.rotated_policy()
        rotated=self.authenticate_root(policy,("root1","root2","root4"),
                                       previous=self.root,minimum=2)
        bad=self.signed_bundle(rotated,release_signer="release1")
        with self.assertRaisesRegex(gate.TrustRejected,"Revoked"):
            self.verify(bad)
        good=self.signed_bundle(rotated,release_signer="release2")
        self.assertEqual(self.verify(good).root_version,2)

    def test_16_retired_key_cannot_be_activated_without_removing_revocation(self):
        policy=self.rotated_policy()
        rotated=self.authenticate_root(policy,("root1","root2","root4"),
                                       previous=self.root,minimum=2)
        policy3={**policy,"version":3,"issued_at":NOW-300,
                 "role_keys":{**policy["role_keys"],"release":self.public_map("release1")},
                 "revoked_key_ids":["release1","release2","root1"]}
        with self.assertRaisesRegex(gate.TrustRejected,"Revoked"):
            self.authenticate_root(policy3,("root2","root3"),previous=rotated,
                                   minimum=3)

    def test_17_wrong_role_signed_source_document_denied(self):
        payload=self.signed_bundle(source_signer="builder1")
        with self.assertRaisesRegex(gate.TrustRejected,"not authorized"):
            self.verify(payload)

    def test_18_release_signer_cannot_act_as_builder(self):
        payload=self.signed_bundle(builder_signer="release1")
        with self.assertRaisesRegex(gate.TrustRejected,"not authorized"):
            self.verify(payload)

    def test_19_outside_attacker_signature_not_authorized(self):
        self.keys["rogue"]=Ed25519PrivateKey.generate()
        payload=self.signed_bundle(release_signer="rogue")
        with self.assertRaisesRegex(gate.TrustRejected,"not authorized"):
            self.verify(payload)

    def test_20_source_repository_or_branch_mismatch_denied(self):
        for change in ({"repo":"github.com/attacker/flight"},
                       {"ref":"refs/heads/unreviewed"}):
            with self.subTest(change=change):
                with self.assertRaisesRegex(gate.TrustRejected,"unauthorized"):
                    self.verify(self.signed_bundle(source_mod=change))

    def test_21_source_sha_must_match_independently_reviewed_commit_and_tree(self):
        bundle=self.signed_bundle()
        with self.assertRaisesRegex(gate.TrustRejected,"independently reviewed"):
            self.verify(bundle,expected_commit="f"*40)
        with self.assertRaisesRegex(gate.TrustRejected,"independently reviewed"):
            self.verify(bundle,expected_tree_sha256="e"*64)

    def test_22_trusted_builder_workflow_mismatch_denied_even_if_signed(self):
        payload=self.signed_bundle(build_mod={
            "builder_workflow":"github.com/attacker/workflows/release.yml"})
        with self.assertRaisesRegex(gate.TrustRejected,"Builder attestation"):
            self.verify(payload)

    def test_23_forged_builder_source_attestation_link_denied(self):
        payload=self.signed_bundle(build_mod={"source_attestation_sha256":"0"*64})
        with self.assertRaisesRegex(gate.TrustRejected,"Builder attestation"):
            self.verify(payload)

    def test_24_builder_artifact_hash_or_size_mismatch_denied(self):
        for change in ({"artifact_sha256":"0"*64},
                       {"artifact_size":len(ARTIFACT)+1}):
            with self.subTest(change=change):
                with self.assertRaises(gate.TrustRejected):
                    self.verify(self.signed_bundle(build_mod=change))

    def test_25_release_signer_wrong_platform_arch_channel_or_app_denied(self):
        for change in ({"platform":"windows"},{"architecture":"arm64"},
                       {"channel":"production"},{"app_id":"fake-tihulu"}):
            with self.subTest(change=change):
                with self.assertRaisesRegex(gate.TrustRejected,"Unauthorized release"):
                    self.verify(self.signed_bundle(release_mod=change))

    def test_26_release_must_bind_exact_builder_and_source_signatures(self):
        for change in ({"source_attestation_sha256":"0"*64},
                       {"builder_attestation_sha256":"0"*64},
                       {"recipe_sha256":"0"*64}):
            with self.subTest(change=change):
                with self.assertRaises(gate.TrustRejected):
                    self.verify(self.signed_bundle(release_mod=change))

    def test_27_copied_release_metadata_tamper_after_signing_denied(self):
        payload=self.signed_bundle()
        raw=payload["release_raw"]
        tampered=raw.replace(b'"sequence":8',b'"sequence":9')
        self.assertNotEqual(raw,tampered)
        with self.assertRaisesRegex(gate.TrustRejected,"signature"):
            self.verify(payload,release_raw=tampered)

    def test_28_invalid_actual_artifact_bytes_denied(self):
        payload=self.signed_bundle()
        with self.assertRaisesRegex(gate.TrustRejected,"Builder attestation"):
            self.verify(payload,artifact=b"foreign-unsigned-fixture")
        with self.assertRaises(gate.TrustRejected):
            self.verify(payload,artifact=b"")
        with self.assertRaises(gate.TrustRejected):
            self.verify(payload,artifact=b"x"*(gate.MAX_ARTIFACT+1))

    def test_29_release_sequence_and_signed_root_version_enforced(self):
        with self.assertRaisesRegex(gate.TrustRejected,"Release root"):
            self.verify(self.signed_bundle(),minimum_sequence=9)
        with self.assertRaisesRegex(gate.TrustRejected,"rollback"):
            self.verify(self.signed_bundle(),minimum_root_version=2)
        with self.assertRaisesRegex(gate.TrustRejected,"Release root"):
            self.verify(self.signed_bundle(release_mod={"root_version":2}))

    def test_30_expired_or_prematurely_valid_root_denied_by_caller_time(self):
        with self.assertRaises(gate.TrustRejected):
            self.authenticate_root(now=NOW+1001)
        with self.assertRaises(gate.TrustRejected):
            self.authenticate_root(now=NOW-1001)
        with self.assertRaises(gate.TrustRejected):
            self.verify(self.signed_bundle(),now=NOW+1001)

    def test_31_positive_limit_unadvanced_floor_allows_same_signed_replay(self):
        # POSITIVE PRODUCTION HOLD: sequence and root floors supplied from
        # external caller; no persisted monotonic counter exists here.
        bundle=self.signed_bundle()
        result=self.verify(bundle)
        repeated=self.verify(bundle)
        self.assertEqual(result, repeated)

    def test_32_positive_limit_forged_self_pin_is_not_out_of_band_auth(self):
        # POSITIVE PRODUCTION HOLD: an attacker controlling both trusted
        # public keys AND their "pin" fingerprint can self-certify an entire
        # unrelated quorum. A real bootstrap needs an independent medium.
        rogue={id_: Ed25519PrivateKey.generate()
               for id_ in ("root1","root2","root3")}
        rogue_public={k:v.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw).hex()
            for k,v in rogue.items()}
        rogue_pins=gate.pin_bootstrap_roots(
            rogue_public,2,gate.pin_digest(rogue_public,2))
        policy={**self.root_policy,"root_keys":rogue_public}
        raw=gate.canonical(policy)
        signatures={k:rogue[k].sign(gate.ROOT_DOMAIN+raw).hex()
                    for k in ("root1","root2")}
        accepted=gate.verify_root_policy(
            raw,signatures,now=NOW,minimum_version=1,bootstrap=rogue_pins)
        self.assertEqual(accepted.version,1)
        self.assertNotEqual(dict(accepted.root_keys),dict(self.pins.keys))


    def test_33_expired_previous_trusted_root_cannot_rotate_without_recovery(self):
        policy=self.rotated_policy()
        policy["issued_at"]=NOW+1001
        policy["expires_at"]=NOW+1400
        with self.assertRaisesRegex(gate.TrustRejected,"Expired previous root"):
            self.authenticate_root(policy,("root1","root2","root4"),
                                   previous=self.root,minimum=2,now=NOW+1001)

    def test_34_signer_authority_cannot_switch_roles_by_reusing_key_id(self):
        policy=self.rotated_policy()
        self.keys["source2"]=Ed25519PrivateKey.generate()
        policy["role_keys"]={
            **policy["role_keys"],
            "source":self.public_map("source2"),
            "release":self.public_map("source1"),
        }
        with self.assertRaisesRegex(gate.TrustRejected,"cannot change signer role"):
            self.authenticate_root(policy,("root1","root2","root4"),
                                   previous=self.root,minimum=2)


if __name__=="__main__":
    unittest.main(verbosity=2)
