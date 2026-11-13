#!/usr/bin/env python3
"""Ephemeral TEST-ONLY Ed25519 root/provenance adversarial acceptance.

Private keys are generated in volatile CI test memory only, not committed,
written to files, logged, published, installed or reused for release.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import flight_root_provenance_ci as chain
from tools import flight_signed_installer_ci_prototype as gate

NOW = 1800000000
DATA = b"CI-ONLY-EPHEMERAL-ROOT-AND-PROVENANCE-ARTIFACT"
SHA = hashlib.sha256(DATA).hexdigest()


def fresh_key():
    return Ed25519PrivateKey.generate()  # RAM-ONLY fixture, NEVER production


def public(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


@unittest.skipUnless(os.name == "posix", "Linux-only CI authority fixture")
class RootProvenanceTests(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI") != "true"
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("Only disposable GitHub-hosted Linux CI")
        self.tmp = tempfile.TemporaryDirectory(
            prefix="flight-ci-authority-", dir=os.environ["RUNNER_TEMP"])
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "ci-image.bin"
        self.source.write_bytes(DATA)
        self.source.chmod(0o600)
        self.root_key = fresh_key()
        self.release_key = fresh_key()
        self.builder_key = fresh_key()
        self.anchor = chain.RootAnchor("ci-root", public(self.root_key), 1, 3)
        self.root = {
            "schema": 1, "root_id": "ci-root",
            "root_public_key": self.anchor.public_key.hex(),
            "epoch": 1, "version": 3, "expires_at": NOW + 3600,
            "app_id": gate.APP_ID, "channel": gate.CHANNEL,
            "source_repo": chain.SOURCE, "workflow": "flight-build-ci",
            "minimum_release_sequence": 25,
            "revoked_key_ids": [],
            "signers": [
                self.rule("release-key", self.release_key, "release"),
                self.rule("builder-key", self.builder_key, "builder")
            ]
        }
        self.release = {
            "schema": 1, "app_id": gate.APP_ID, "channel": gate.CHANNEL,
            "platform": "linux", "architecture": "x86_64",
            "artifact_name": self.source.name,
            "artifact_size": len(DATA), "artifact_sha256": SHA,
            "sequence": 30, "issued_at": NOW-100, "expires_at": NOW+100,
            "source_commit": "a"*40, "key_id": "release-key"
        }
        self.attest = {
            "schema": 1, "builder_id": "builder-key",
            "source_repo": chain.SOURCE, "source_commit": "a"*40,
            "workflow": "flight-build-ci", "run_id": "ci123", "build_id": "build123",
            "app_id": gate.APP_ID, "channel": gate.CHANNEL,
            "platform": "linux", "architecture": "x86_64",
            "artifact_name": self.source.name,
            "artifact_size": len(DATA), "artifact_sha256": SHA,
            "release_sequence": 30, "issued_at": NOW-100,
            "expires_at": NOW+100
        }

    def rule(self, keyid, key, role):
        return {
            "key_id": keyid, "public_key": public(key).hex(), "role": role,
            "platform": "linux", "architecture": "x86_64",
            "expires_at": NOW + 2500
        }

    def envelopes(self, *, root=None, release=None, attest=None,
                  root_key=None, release_key=None, builder_key=None):
        rr = gate.canonical_bytes(self.root if root is None else root)
        lr = gate.canonical_bytes(self.release if release is None else release)
        ar = gate.canonical_bytes(self.attest if attest is None else attest)
        return (
            rr, (self.root_key if root_key is None else root_key)
                .sign(chain.ROOT_DOMAIN + rr),
            lr, (self.release_key if release_key is None else release_key)
                .sign(gate.DOMAIN + lr),
            ar, (self.builder_key if builder_key is None else builder_key)
                .sign(chain.BUILD_DOMAIN + ar),
        )

    def check(self, *, envelopes=None, anchor=None, minimum=29,
              now=NOW, seal=False, source=None, platform="linux",
              architecture="x86_64"):
        rr, rs, lr, ls, ar, att_sig = (
            self.envelopes() if envelopes is None else envelopes)
        if seal:
            return chain.verify_provenance_and_seal(
                self.source if source is None else source,
                rr, rs, self.anchor if anchor is None else anchor,
                lr, ls, ar, att_sig,
                minimum_sequence=minimum, now=now)
        return chain.verify_release_provenance(
            rr, rs, self.anchor if anchor is None else anchor,
            lr, ls, ar, att_sig, platform=platform,
            architecture=architecture, minimum_sequence=minimum, now=now)

    def reject(self, *, pattern=None, **kwargs):
        with self.assertRaises(gate.TrustRejected) as ctx:
            maybe = self.check(**kwargs)
            if hasattr(maybe, "close"):
                maybe.close()
        if pattern:
            self.assertIn(pattern, str(ctx.exception))

    def test_01_anchor_pinned_root_release_builder_and_sealed_bytes(self):
        with self.check(seal=True) as fixture:
            self.assertEqual(fixture.read(), DATA)
            self.assertEqual(fixture.metadata["artifact_sha256"], SHA)
            self.assertEqual(fixture.verified_length, len(DATA))
            self.assertFalse(hasattr(fixture, "fd"))
        approval = self.check()
        self.assertEqual(approval.root_id, self.anchor.root_id)
        self.assertEqual(approval.root_version, 3)
        self.assertEqual(approval.builder_id, "builder-key")
        self.assertEqual(approval.source_repo, chain.SOURCE)
        with self.assertRaises(FrozenInstanceError):
            approval.root_version = 0

    def test_02_attacker_signed_root_rejected_by_independent_pin(self):
        rogue = fresh_key()
        fake = {**self.root, "root_public_key": public(rogue).hex()}
        self.reject(envelopes=self.envelopes(root=fake, root_key=rogue),
                    pattern="unpinned")

    def test_03_root_field_changed_after_signature_is_refused(self):
        e = list(self.envelopes())
        fake = {**self.root, "minimum_release_sequence": 0}
        e[0] = gate.canonical_bytes(fake)
        self.reject(envelopes=tuple(e), pattern="signature")

    def test_04_wrong_release_signer_signature_rejected(self):
        rogue = fresh_key()
        self.reject(envelopes=self.envelopes(release_key=rogue),
                    pattern="signature")

    def test_05_wrong_builder_signer_signature_rejected(self):
        rogue = fresh_key()
        self.reject(envelopes=self.envelopes(builder_key=rogue),
                    pattern="signature")

    def test_06_cross_role_signer_confusion_denied(self):
        rogue_release = {**self.release, "key_id": "builder-key"}
        self.reject(envelopes=self.envelopes(release=rogue_release),
                    pattern="role")
        wrong_builder = {**self.attest, "builder_id": "release-key"}
        self.reject(envelopes=self.envelopes(attest=wrong_builder),
                    pattern="role")

    def test_07_revoked_old_release_key_denied_by_signed_root(self):
        newkey = fresh_key()
        root = {**self.root,
                "signers": [
                    self.rule("release-new", newkey, "release"),
                    self.rule("builder-key", self.builder_key, "builder")
                ], "revoked_key_ids": ["release-key"]}
        self.reject(envelopes=self.envelopes(root=root),
                    pattern="revoked")
        changed = {**self.release, "key_id": "release-new"}
        rr, rs, lr, ls, ar, ats = self.envelopes(
            root=root, release=changed, release_key=newkey)
        good = self.check(envelopes=(rr,rs,lr,ls,ar,ats))
        self.assertEqual(good.release.key_id,"release-new")

    def test_08_unknown_signer_key_and_unknown_builder_denied(self):
        self.reject(envelopes=self.envelopes(
            release={**self.release, "key_id": "unknown"}),
            pattern="lacks root-authorized")
        self.reject(envelopes=self.envelopes(
            attest={**self.attest, "builder_id": "untrusted"}),
            pattern="lacks root-authorized")

    def test_09_signed_wrong_artifact_digest_or_size_attestation_denied(self):
        for delta in ({"artifact_sha256": "0"*64},
                      {"artifact_size": len(DATA) + 1},
                      {"artifact_name": "wrong.bin"}):
            with self.subTest(delta=delta):
                self.reject(envelopes=self.envelopes(
                    attest={**self.attest, **delta}),pattern="bind")

    def test_10_signed_build_source_commit_mismatch_denied(self):
        self.reject(envelopes=self.envelopes(
            attest={**self.attest,"source_commit": "b"*40}), pattern="bind")

    def test_11_wrong_build_repository_denied_even_if_builder_signed(self):
        self.reject(envelopes=self.envelopes(attest={
            **self.attest, "source_repo": "Attacker/looks-real"}),
            pattern="provenance")

    def test_12_wrong_builder_workflow_denied(self):
        self.reject(envelopes=self.envelopes(attest={
            **self.attest, "workflow": "untrusted-pipeline"}),
            pattern="provenance")

    def test_13_validly_signed_wrong_platform_and_arch_denied(self):
        self.reject(platform="windows",pattern="platform")
        self.reject(architecture="arm64",pattern="platform")
        self.reject(envelopes=self.envelopes(
            release={**self.release, "platform":"windows"}),pattern="signature/policy")

    def test_14_independent_minimum_release_sequence_downgrade_denied(self):
        self.reject(minimum=31,pattern="rollback")
        lower = {**self.release, "sequence": 24}
        loweratt = {**self.attest, "release_sequence": 24}
        self.reject(envelopes=self.envelopes(
            release=lower, attest=loweratt),pattern="rollback")

    def test_15_root_policy_expired_denied(self):
        self.reject(now=NOW + 3700,pattern="expired")

    def test_16_duplicate_root_fields_and_noncanonical_root_denied(self):
        e = list(self.envelopes())
        e[0] = e[0][:-1] + b',"schema":1}'
        self.reject(envelopes=tuple(e),pattern="Duplicate")
        e = list(self.envelopes())
        e[0] = json.dumps(self.root,sort_keys=True).encode("utf-8")
        self.reject(envelopes=tuple(e),pattern="Noncanonical")

    def test_17_duplicate_build_fields_and_noncanonical_build_denied(self):
        e = list(self.envelopes())
        e[4] = e[4][:-1] + b',"schema":1}'
        self.reject(envelopes=tuple(e),pattern="Duplicate")
        e = list(self.envelopes())
        e[4] = json.dumps(self.attest,sort_keys=True).encode("utf-8")
        self.reject(envelopes=tuple(e),pattern="Noncanonical")

    def test_18_root_rotation_requires_both_old_and_new_signatures(self):
        next_root = fresh_key()
        future = {**self.root, "root_public_key": public(next_root).hex(),
                  "epoch":2,"version":4}
        raw = gate.canonical_bytes(future)
        old = self.root_key.sign(chain.ROOT_DOMAIN + raw)
        new = next_root.sign(chain.ROOT_DOMAIN + raw)
        nxt = chain.rotate_root_anchor(
            self.anchor, raw, old, new, now=NOW)
        self.assertEqual(nxt.minimum_epoch, 2)
        self.assertEqual(nxt.minimum_version, 4)
        parsed = chain.verify_root_policy(raw,new,nxt,now=NOW)
        self.assertEqual(parsed.root_public_key,public(next_root))

    def test_19_root_rotation_missing_old_or_new_authority_rejected(self):
        next_root=fresh_key()
        future={**self.root,"root_public_key":public(next_root).hex(),
                "epoch":2,"version":4}
        raw=gate.canonical_bytes(future)
        old=self.root_key.sign(chain.ROOT_DOMAIN + raw)
        new=next_root.sign(chain.ROOT_DOMAIN + raw)
        rogue=fresh_key()
        with self.assertRaises(chain.AuthorityRejected):
            chain.rotate_root_anchor(
                self.anchor,raw,rogue.sign(chain.ROOT_DOMAIN+raw),new,now=NOW)
        with self.assertRaises(chain.AuthorityRejected):
            chain.rotate_root_anchor(
                self.anchor,raw,old,rogue.sign(chain.ROOT_DOMAIN+raw),now=NOW)

    def test_20_rotated_root_pin_does_not_accept_old_root_policy(self):
        nxt_key=fresh_key()
        future={**self.root,"root_public_key":public(nxt_key).hex(),
                "epoch":2,"version":4}
        raw=gate.canonical_bytes(future)
        nxt=chain.rotate_root_anchor(
            self.anchor,raw,self.root_key.sign(chain.ROOT_DOMAIN+raw),
            nxt_key.sign(chain.ROOT_DOMAIN+raw),now=NOW)
        rr,rs,*_ = self.envelopes()
        with self.assertRaisesRegex(chain.AuthorityRejected,"root"):
            chain.verify_root_policy(rr,rs,nxt,now=NOW)

    def test_21_rollback_old_root_version_rejected_by_anchor(self):
        anchor=chain.RootAnchor("ci-root",public(self.root_key),1,4)
        self.reject(anchor=anchor,pattern="rollback")

    def test_22_signer_key_expiry_denied_even_if_root_valid(self):
        r={**self.root,"signers":[
            {**self.root["signers"][0],"expires_at":NOW-1},
            self.root["signers"][1]]}
        self.reject(envelopes=self.envelopes(root=r), pattern="expired")

    def test_23_unexpected_nested_signer_and_revocation_state_denied(self):
        for change in (
            {"signers":[{**self.root["signers"][0],"roles":["release"]},
                        self.root["signers"][1]]},
            {"revoked_key_ids":["builder-key"],"signers":self.root["signers"]},
            {"revoked_key_ids":["bad","bad"]},
            {"signers":[{**self.root["signers"][0],"public_key":"0"*64},
                        self.root["signers"][1]]},
        ):
            with self.subTest(change=change):
                e=self.envelopes(root={**self.root,**change})
                with self.assertRaises(gate.TrustRejected):
                    self.check(envelopes=e)

    def test_24_source_rename_after_open_uses_only_original_verified_bytes(self):
        real=gate._open_source_once
        saved=self.folder/"held-original"
        events=[]
        def replace(path,runner):
            fd=real(path,runner)
            events.append(True)
            self.source.rename(saved)
            self.source.write_bytes(b"ATTACKER-PATH-REPLACED")
            return fd
        with patch.object(gate,"_open_source_once",new=replace):
            with self.check(seal=True) as result:
                self.assertEqual(result.read(),DATA)
        self.assertEqual(events,[True])
        self.assertEqual(saved.read_bytes(),DATA)

    def test_25_inplace_source_tamper_refused(self):
        real=gate._open_source_once
        def tamper(path,runner):
            fd=real(path,runner)
            self.source.write_bytes(b"UNTRUSTED")
            return fd
        with patch.object(gate,"_open_source_once",new=tamper):
            self.reject(seal=True)

    def test_26_ci_safety_interlock_denies_host_environment(self):
        with patch.dict(os.environ,{"CI":"false"}):
            self.reject(pattern="CI-only")

    def test_27_build_attestation_timestamp_or_release_sequence_denied(self):
        self.reject(envelopes=self.envelopes(
            attest={**self.attest,"expires_at":NOW-1}),pattern="freshness")
        self.reject(envelopes=self.envelopes(
            attest={**self.attest,"release_sequence":1}),pattern="bind")

    def test_28_trusted_bootstrap_is_external_not_self_asserted(self):
        # POSITIVE THREAT BOUNDARY: if attacker controls *external* root pin,
        # they can authorize any signer. Not a cryptographic flaw/GO.
        attacker_root=fresh_key()
        fake={**self.root,"root_public_key":public(attacker_root).hex()}
        anchor=chain.RootAnchor("ci-root",public(attacker_root),1,3)
        rr,rs,lr,ls,ar,ats=self.envelopes(
            root=fake,root_key=attacker_root)
        accepted=self.check(envelopes=(rr,rs,lr,ls,ar,ats),anchor=anchor)
        self.assertEqual(accepted.root_id,"ci-root")
        # Hence true OS-attested root bootstrap is P1 HOLD.

if __name__ == "__main__":
    unittest.main(verbosity=2)
