#!/usr/bin/env python3
"""CI-ONLY P1-ROOT/PROVENANCE trust model. NOT a production trust anchor.

There are deliberately NO embedded production public or private keys.
Caller pins MUST be authenticated out-of-band from the artifact channel.
This testable design has no installer, system broker or durable rollback state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import sys
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

TRUST_DOMAIN = "tihulu-flight-radar/ci-fixture"
APP = "tihulu-flight-radar-ci-fixture"
CHANNEL = "disposable-ci"
ROOT_DOMAIN = b"TIHULU_FLIGHT_ROOT_POLICY_CI_V1\x00"
SOURCE_DOMAIN = b"TIHULU_FLIGHT_SOURCE_ATTEST_CI_V1\x00"
BUILDER_DOMAIN = b"TIHULU_FLIGHT_BUILDER_ATTEST_CI_V1\x00"
RELEASE_DOMAIN = b"TIHULU_FLIGHT_RELEASE_ATTEST_CI_V1\x00"
ROLES = ("source", "builder", "release")
MAX_JSON = 8192
MAX_ARTIFACT = 1024 * 1024
MAX_ROOT_VALIDITY = 14 * 86400
HEX32 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64SIG = re.compile(r"[0-9a-f]{128}\Z")
KEYID = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
ARTNAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,79}\Z")
ROOT_FIELDS = frozenset((
    "schema", "domain", "version", "issued_at", "expires_at",
    "threshold", "root_keys", "role_keys", "revoked_key_ids",
    "revoked_key_fingerprints",
    "source_repo", "source_ref", "builder_workflow",
))
SOURCE_FIELDS = frozenset(("schema", "key_id", "repo", "ref", "commit", "tree_sha256"))
BUILDER_FIELDS = frozenset((
    "schema", "key_id", "repo", "ref", "commit", "tree_sha256",
    "source_attestation_sha256", "artifact_sha256", "artifact_size",
    "recipe_sha256", "materials_sha256", "builder_workflow",
))
RELEASE_FIELDS = frozenset((
    "schema", "key_id", "root_version", "app_id", "channel",
    "platform", "architecture", "artifact_name", "artifact_size",
    "artifact_sha256", "sequence", "repo", "ref", "commit", "tree_sha256",
    "recipe_sha256", "materials_sha256",
    "source_attestation_sha256", "builder_attestation_sha256",
))


class TrustRejected(RuntimeError):
    """Fail closed on unsigned, untrusted or inconsistent CI fixture policy."""


def deny(reason: str):
    raise TrustRejected(reason)


def _require_ci():
    if (sys.platform != "linux" or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or not os.environ.get("RUNNER_TEMP")):
        deny("Only disposable GitHub-hosted Linux CI fixture is allowed")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _unique_pairs(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            deny("Duplicate signed JSON member")
        value[k] = v
    return value


def _decode(raw, expected_fields):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_JSON:
        deny("Missing or oversized signed metadata")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (ValueError, TypeError, UnicodeError):
        deny("Malformed signed JSON")
    if type(parsed) is not dict or set(parsed) != expected_fields:
        deny("Unexpected signed schema fields")
    try:
        if canonical(parsed) != raw:
            deny("Noncanonical signed JSON")
    except (ValueError, TypeError, OverflowError):
        deny("Unsupported signed JSON value")
    return parsed


def _name(value, pattern=KEYID):
    return type(value) is str and pattern.fullmatch(value) is not None


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _key_map(obj, label):
    if type(obj) is not dict or not 1 <= len(obj) <= 16:
        deny("Empty or oversized " + label + " roster")
    result = {}
    for key_id, hexkey in obj.items():
        if not _name(key_id) or not _name(hexkey, HEX32):
            deny("Malformed " + label + " ID or Ed25519 public key")
        result[key_id] = bytes.fromhex(hexkey)
    if len(set(result.values())) != len(result):
        deny("Distinct signing authorities cannot share one key")
    return result


def key_fingerprint(public_key):
    """Domain-separated SHA-256 of the immutable 32-byte Ed25519 public key.

    Revocation attaches to KEY MATERIAL, never merely the replaceable ID.
    No private key, production signing authority or secret is constructed.
    """
    if type(public_key) is not bytes or len(public_key) != 32:
        deny("Invalid Ed25519 public key material for fingerprint")
    return hashlib.sha256(
        b"TIHULU_FLIGHT_ED25519_KEY_TOMBSTONE_V1\0" + public_key
    ).hexdigest()


def _revocation_fingerprints(value, revoked_ids):
    """Signed ID-to-material tombstones, canonical and complete.

    Old revoked IDs with unknown original public bytes MUST have an
    authenticated fingerprint supplied by the original signed policy.
    """
    if type(value) is not dict or set(value) != set(revoked_ids):
        deny("Signed key fingerprint ledger must cover exact revoked IDs")
    for key_id, fingerprint in value.items():
        if not _name(key_id) or not _name(fingerprint, HEX32):
            deny("Invalid signed revoked key fingerprint")
    if len(set(value.values())) != len(value):
        deny("Revocation fingerprint ledger aliases revoked key material")
    return dict(value)


def _root_roster(policy):
    root = _key_map(policy["root_keys"], "root")
    roles = policy["role_keys"]
    if type(roles) is not dict or set(roles) != set(ROLES):
        deny("Unknown or missing signer role")
    role_keys = {r: _key_map(roles[r], r) for r in ROLES}
    all_rosters = [root, *(role_keys[r] for r in ROLES)]
    all_ids = [k for roster in all_rosters for k in roster]
    all_values = [v for roster in all_rosters for v in roster.values()]
    if len(set(all_ids)) != len(all_ids) or len(set(all_values)) != len(all_values):
        deny("Root/source/builder/release signer authority must be independent")
    return root, role_keys


@dataclass(frozen=True, slots=True)
class BootstrapPins:
    """Out-of-band pinned root material; creation does NOT authenticate its origin."""
    keys: object
    threshold: int
    pin_sha256: str


def pin_digest(keys, threshold):
    """Hash an independently distributed roster. A hash supplied by the
    same untrusted artifact channel is NOT an authenticated anchor.
    """
    if not _integer(threshold, 2, 16):
        deny("Bootstrap must use threshold >= 2")
    keymap = _key_map(keys, "bootstrap")
    if threshold > len(keymap):
        deny("Bootstrap threshold exceeds root roster")
    roster = {k: v.hex() for k, v in keymap.items()}
    return hashlib.sha256(canonical({
        "schema": 1, "domain": TRUST_DOMAIN,
        "threshold": threshold, "keys": roster,
    })).hexdigest()


def pin_bootstrap_roots(out_of_band_keys, threshold, authenticated_pin_sha256):
    """The caller MUST supply key bytes and fingerprint from separately
    authenticated media. This function cannot prove their real-world origin.
    """
    _require_ci()
    if not _name(authenticated_pin_sha256, HEX32):
        deny("Independently authenticated root pin SHA-256 is required")
    actual = pin_digest(out_of_band_keys, threshold)
    if actual != authenticated_pin_sha256:
        deny("Bootstrapped public-key roster differs from independent anchor")
    keys = _key_map(out_of_band_keys, "bootstrap")
    return BootstrapPins(MappingProxyType(keys), threshold, actual)


@dataclass(frozen=True, slots=True, init=False)
class RootAuthority:
    """Signed root policy, copied away from all untrusted input dictionaries.

    Constructor denied: only verify_root_policy may mint a RootAuthority.
    Python reflection is NOT a malicious same-interpreter security barrier.
    """
    version: int
    threshold: int
    root_keys: object
    role_keys: object
    revoked_key_ids: frozenset
    revoked_key_fingerprints: object
    source_repo: str
    source_ref: str
    builder_workflow: str
    issued_at: int
    expires_at: int

    def __init__(self, *_args, **_kwargs):
        deny("RootAuthority requires authenticated threshold endorsements")


def _sig_bytes(hexsig):
    if not _name(hexsig, HEX64SIG):
        deny("Malformed Ed25519 signature")
    return bytes.fromhex(hexsig)


def _verify(key, signature, domain, raw):
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(signature, domain + raw)
    except (InvalidSignature, ValueError):
        deny("Ed25519 signature authentication failed")


def _quorum(raw, signatures, old_roots, old_threshold, new_roots, new_threshold):
    if type(signatures) is not dict or not 1 <= len(signatures) <= 32:
        deny("Root endorsements required")
    authorized = {**old_roots, **new_roots}
    if set(signatures) - set(authorized):
        deny("Unknown root endorser")
    if any(k in old_roots and k in new_roots and old_roots[k] != new_roots[k]
           for k in authorized):
        deny("Existing root ID cannot silently change its key")
    for key_id, raw_sig in signatures.items():
        if not _name(key_id):
            deny("Invalid root endorser key identifier")
        _verify(authorized[key_id], _sig_bytes(raw_sig), ROOT_DOMAIN, raw)
    # Count DISTINCT ED25519 PUBLIC KEY MATERIAL, not attacker-chosen aliases.
    old_signed_material = {old_roots[k] for k in signatures if k in old_roots}
    new_signed_material = {new_roots[k] for k in signatures if k in new_roots}
    if len(old_signed_material) < old_threshold:
        deny("Previous trusted root threshold not met")
    if len(new_signed_material) < new_threshold:
        deny("New root threshold not met")


def verify_root_policy(raw, endorsements, *, now, minimum_version,
                       bootstrap=None, previous=None):
    """Initial roots require externally pinned public keys.
    Rotations require BOTH old trusted AND new proposed root quorums.
    minimum_version is supplied by an external trusted state authority;
    this module does NOT persist any rollback floor.
    """
    _require_ci()
    if not _integer(now, 0, 2**63-1) or not _integer(minimum_version, 1, 2**31-1):
        deny("Trusted time and version floor required")
    if (bootstrap is None) == (previous is None):
        deny("Provide exactly one bootstrap authority or verified previous root")
    value = _decode(raw, ROOT_FIELDS)
    if (value["schema"] != 1 or type(value["schema"]) is not int
            or value["domain"] != TRUST_DOMAIN
            or not _integer(value["version"], 1, 2**31-1)
            or not _integer(value["threshold"], 2, 16)
            or not _integer(value["issued_at"], 0, 2**63-1)
            or not _integer(value["expires_at"], 0, 2**63-1)
            or not value["issued_at"] <= now <= value["expires_at"]
            or not 0 < value["expires_at"] - value["issued_at"] <= MAX_ROOT_VALIDITY):
        deny("Invalid signed root schema, epoch, or validity")
    for field in ("source_repo", "source_ref", "builder_workflow"):
        val = value[field]
        if type(val) is not str or not 1 <= len(val) <= 180 or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-:"
            for c in val):
            deny("Invalid trusted provenance identity " + field)
    if (not value["source_repo"].startswith("github.com/")
            or not value["source_ref"].startswith("refs/heads/")
            or not value["builder_workflow"].startswith("github.com/")):
        deny("Unsupported provenance authority identifier")
    new_roots, roles = _root_roster(value)
    if value["threshold"] > len(new_roots):
        deny("Root threshold exceeds available signers")
    revoked = value["revoked_key_ids"]
    if (type(revoked) is not list or any(not _name(k) for k in revoked)
            or revoked != sorted(set(revoked))):
        deny("Revocation ledger must be sorted and unique")
    active = set(new_roots) | set().union(*(set(roles[r]) for r in ROLES))
    if active & set(revoked):
        deny("Revoked signer cannot retain an active authority")
    ledger = _revocation_fingerprints(value["revoked_key_fingerprints"], revoked)
    active_keys = {**new_roots, **{k: v for r in ROLES for k, v in roles[r].items()}}
    denied_material = set(ledger.values())
    if any(key_fingerprint(pub) in denied_material for pub in active_keys.values()):
        deny("Revoked Ed25519 key material/fingerprint cannot regain any authority")
    if value["version"] < minimum_version:
        deny("Root policy rollback rejected by trusted caller floor")
    if previous is None:
        if type(bootstrap) is not BootstrapPins or value["version"] != 1:
            deny("Initial version 1 requires a pinned trusted bootstrap")
        if dict(bootstrap.keys) != new_roots or bootstrap.threshold != value["threshold"]:
            deny("Initial root roster must exactly match external root pins")
        old_roots, old_threshold = dict(bootstrap.keys), bootstrap.threshold
    else:
        if type(previous) is not RootAuthority:
            deny("Previous root must be already signature-authenticated")
        if not previous.issued_at <= now <= previous.expires_at:
            deny("Expired previous root requires manual offline recovery")
        if value["version"] != previous.version + 1:
            deny("Root rotation must advance exactly one version")
        if value["issued_at"] < previous.issued_at:
            deny("Root policy issued_at regressed")
        if not previous.revoked_key_ids.issubset(set(revoked)):
            deny("Root key revocation ledger cannot shrink")
        # Every prior authenticated material tombstone is immutable
        # across ALL epochs, including historical IDs no longer active.
        for retired_id, fp in previous.revoked_key_fingerprints.items():
            if ledger.get(retired_id) != fp:
                deny("Root key material fingerprint ledger cannot shrink/change")
        old_active_keys = {
            **dict(previous.root_keys),
            **{k: v for r in ROLES for k, v in previous.role_keys[r].items()},
        }
        old_active = set(old_active_keys)
        if not (old_active - active).issubset(set(revoked)):
            deny("Retired authority must be explicitly revoked")
        for retired_id in old_active - active:
            expected = key_fingerprint(old_active_keys[retired_id])
            if ledger.get(retired_id) != expected:
                deny("Retired authority fingerprint tombstone missing or forged")
        for key_id in old_active & active:
            old_role = next((r for r in ROLES
                             if key_id in previous.role_keys[r]), "root")
            new_role = next((r for r in ROLES
                             if key_id in roles[r]), "root")
            if old_role != new_role:
                deny("Existing authority ID cannot change signer role")
            old_key = (dict(previous.root_keys)
                       | {k: v for r in ROLES for k, v in previous.role_keys[r].items()})[key_id]
            new_key = (new_roots
                       | {k: v for r in ROLES for k, v in roles[r].items()})[key_id]
            if old_key != new_key:
                deny("Existing authority ID reused with a different public key")
        old_roots, old_threshold = dict(previous.root_keys), previous.threshold
    _quorum(raw, endorsements, old_roots, old_threshold, new_roots, value["threshold"])
    approved = RootAuthority.__new__(RootAuthority)
    values = (
        value["version"], value["threshold"], MappingProxyType(dict(new_roots)),
        MappingProxyType({r: MappingProxyType(dict(roles[r])) for r in ROLES}),
        frozenset(revoked), MappingProxyType(dict(ledger)),
        value["source_repo"], value["source_ref"],
        value["builder_workflow"], value["issued_at"], value["expires_at"],
    )
    for field_name, validated in zip(RootAuthority.__dataclass_fields__, values):
        object.__setattr__(approved, field_name, validated)
    return approved


def _role_verify(root, role, document, raw, domain):
    key_id = document["key_id"]
    if not _name(key_id) or key_id in root.revoked_key_ids:
        deny("Revoked or invalid signer")
    key = root.role_keys[role].get(key_id)
    if key is None:
        deny("Signer is not authorized for required role: " + role)
    return key, domain + raw


def _signed_document(root, role, raw, sig, fields_expected, domain):
    value = _decode(raw, fields_expected)
    if type(value["schema"]) is not int or value["schema"] != 1:
        deny("Unsupported provenance schema")
    key, _ = _role_verify(root, role, value, raw, domain)
    _verify(key, _sig_bytes(sig), domain, raw)
    return value


def _hex(value, label, regex=HEX32):
    if not _name(value, regex):
        deny("Malformed " + label)


@dataclass(frozen=True, slots=True, init=False)
class VerifiedProvenance:
    """Bound CI-only provenance evidence, NOT an installer authorization token.
    Constructor denied: verification must complete the full role chain.
    """
    root_version: int
    artifact_sha256: str
    artifact_size: int
    source_commit: str
    tree_sha256: str
    source_attestation_sha256: str
    builder_attestation_sha256: str
    release_sequence: int

    def __init__(self, *_args, **_kwargs):
        deny("VerifiedProvenance requires a source/builder/release authorization chain")


def verify_provenance_bundle(root, *, source_raw, source_signature,
                             builder_raw, builder_signature,
                             release_raw, release_signature, artifact,
                             expected_commit, expected_tree_sha256,
                             expected_platform, expected_arch,
                             minimum_sequence, minimum_root_version, now):
    """Require three DIFFERENT signed authorities (source/build/release),
    plus exact artifact bytes and independent expected source commitment.

    The signatures attest *claims* made by authorized test signers; they
    cannot independently prove that GitHub actually built those bytes.
    """
    _require_ci()
    if type(root) is not RootAuthority:
        deny("Previously verified root policy required")
    if not _integer(now, root.issued_at, root.expires_at):
        deny("Trusted caller time outside authorized root validity")
    if (not _integer(minimum_root_version, 1, 2**31-1)
            or root.version < minimum_root_version
            or not _integer(minimum_sequence, 0, 2**63-1)):
        deny("Trusted root/release rollback floor failed")
    _hex(expected_commit, "independent source commit", HEX40)
    _hex(expected_tree_sha256, "independent tree digest")
    if type(expected_platform) is not str or type(expected_arch) is not str:
        deny("Expected release platform and architecture required")
    if type(artifact) is not bytes or not 0 < len(artifact) <= MAX_ARTIFACT:
        deny("Missing/oversized candidate artifact")
    actual = hashlib.sha256(artifact).hexdigest()

    src = _signed_document(root, "source", source_raw, source_signature,
                           SOURCE_FIELDS, SOURCE_DOMAIN)
    _hex(src["commit"], "source commit", HEX40)
    _hex(src["tree_sha256"], "source tree digest")
    if (src["repo"], src["ref"]) != (root.source_repo, root.source_ref):
        deny("Source attestation from unauthorized repository/ref")
    if (src["commit"], src["tree_sha256"]) != (expected_commit, expected_tree_sha256):
        deny("Source attestation does not match independently reviewed source")
    src_hash = hashlib.sha256(source_raw).hexdigest()

    build = _signed_document(root, "builder", builder_raw, builder_signature,
                             BUILDER_FIELDS, BUILDER_DOMAIN)
    for field in ("tree_sha256", "source_attestation_sha256",
                  "artifact_sha256", "recipe_sha256", "materials_sha256"):
        _hex(build[field], "builder " + field)
    _hex(build["commit"], "builder commit", HEX40)
    if not _integer(build["artifact_size"], 1, MAX_ARTIFACT):
        deny("Invalid signed build artifact size")
    if (build["repo"], build["ref"], build["commit"], build["tree_sha256"]) != (
            src["repo"], src["ref"], src["commit"], src["tree_sha256"]):
        deny("Builder attestation source linkage mismatch")
    if (build["builder_workflow"] != root.builder_workflow
            or build["source_attestation_sha256"] != src_hash
            or build["artifact_sha256"] != actual
            or build["artifact_size"] != len(artifact)):
        deny("Builder attestation chain/artifact mismatch")
    build_hash = hashlib.sha256(builder_raw).hexdigest()

    release = _signed_document(root, "release", release_raw, release_signature,
                               RELEASE_FIELDS, RELEASE_DOMAIN)
    for field in ("tree_sha256", "source_attestation_sha256",
                  "builder_attestation_sha256", "artifact_sha256",
                  "recipe_sha256", "materials_sha256"):
        _hex(release[field], "release " + field)
    _hex(release["commit"], "release commit", HEX40)
    if (release["app_id"] != APP or release["channel"] != CHANNEL
            or release["platform"] != expected_platform
            or release["architecture"] != expected_arch
            or not _name(release["artifact_name"], ARTNAME)
            or ".." in release["artifact_name"]):
        deny("Unauthorized release target, channel or artifact filename")
    if (not _integer(release["root_version"], root.version, root.version)
            or not _integer(release["sequence"], minimum_sequence, 2**63-1)
            or not _integer(release["artifact_size"], len(artifact), len(artifact))):
        deny("Release root/sequence/length policy mismatch")
    fields_to_match = (
        "repo", "ref", "commit", "tree_sha256", "recipe_sha256",
        "materials_sha256", "artifact_sha256", "artifact_size",
    )
    if any(release[field] != build[field] for field in fields_to_match):
        deny("Release signer did not authorize exact builder/source/artifact")
    if (release["source_attestation_sha256"] != src_hash
            or release["builder_attestation_sha256"] != build_hash
            or release["artifact_sha256"] != actual):
        deny("Release chain does not bind source/build/actual artifact")
    record = VerifiedProvenance.__new__(VerifiedProvenance)
    values = (root.version, actual, len(artifact), src["commit"],
              src["tree_sha256"], src_hash, build_hash, release["sequence"])
    for field_name, validated in zip(VerifiedProvenance.__dataclass_fields__, values):
        object.__setattr__(record, field_name, validated)
    return record
