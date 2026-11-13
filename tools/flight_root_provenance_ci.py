#!/usr/bin/env python3
"""CI-ONLY P1-ROOT/PROVENANCE authority-chain prototype, NOT production trust.

All verification anchors come from the CALLER, independently of downloaded
root policy, release and builder attestation. In tests, keys are ephemeral in
RAM, never product-signing keys. This module has NO disk/OS bootstrap,
trusted clock, durable replay state, broker or installer. PUBLIC RELEASE HOLD.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools import flight_signed_installer_ci_prototype as gate

ROOT_DOMAIN = b"TIHULU_FLIGHT_CI_ROOT_POLICY_V1\0"
BUILD_DOMAIN = b"TIHULU_FLIGHT_CI_BUILD_ATTEST_V1\0"
MAX_POLICY = 8192
MAX_ATTEST = 4096
MAX_LIFETIME = 14 * 86400
IDENT = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
SOURCE = "Tihulu/tihulu-flight-radar"
ROOT_FIELDS = frozenset((
    "schema", "root_id", "root_public_key", "epoch", "version", "expires_at",
    "app_id", "channel", "source_repo", "workflow",
    "minimum_release_sequence", "signers", "revoked_key_ids",
))
SIGNER_FIELDS = frozenset((
    "key_id", "public_key", "role", "platform", "architecture", "expires_at",
))
ATTEST_FIELDS = frozenset((
    "schema", "builder_id", "source_repo", "source_commit", "workflow",
    "run_id", "build_id", "app_id", "channel", "platform", "architecture",
    "artifact_name", "artifact_size", "artifact_sha256",
    "release_sequence", "issued_at", "expires_at",
))


class AuthorityRejected(gate.TrustRejected):
    """Reject an unauthenticated or unauthorized CI-only authority chain."""


def deny(reason):
    raise AuthorityRejected(reason)


def _integer(v, *, minimum=0):
    return type(v) is int and v >= minimum


def _text(v):
    return type(v) is str and bool(IDENT.fullmatch(v))


def _public(hex_key):
    if type(hex_key) is not str or len(hex_key) != 64:
        deny("Invalid Ed25519 public key encoding")
    try:
        value = bytes.fromhex(hex_key)
    except ValueError:
        deny("Invalid Ed25519 public key hex")
    if len(value) != 32 or hex_key != value.hex():
        deny("Noncanonical Ed25519 public key encoding")
    return value


def _decode(raw, expected, max_len):
    gate._require_ci()
    if type(raw) is not bytes or not 0 < len(raw) <= max_len:
        deny("Invalid authority metadata size")
    try:
        value = json.loads(raw.decode("utf-8"),
                           object_pairs_hook=gate._unique_pairs)
    except (UnicodeError, ValueError, TypeError):
        deny("Invalid authority JSON")
    if type(value) is not dict or set(value) != expected:
        deny("Unknown/missing authority metadata fields")
    if gate.canonical_bytes(value) != raw:
        deny("Noncanonical authority metadata")
    return value


def _signature(public, signature, domain, raw):
    if type(signature) is not bytes or len(signature) != 64:
        deny("Invalid detached Ed25519 signature length")
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, domain + raw)
    except (InvalidSignature, ValueError):
        deny("Ed25519 authority signature invalid")


@dataclass(frozen=True, slots=True)
class RootAnchor:
    """Caller-owned out-of-band public root pin; NOT established by this code."""
    root_id: str
    public_key: bytes
    minimum_epoch: int
    minimum_version: int


@dataclass(frozen=True, slots=True)
class AuthoritySigner:
    key_id: str
    public_key: bytes
    role: str
    platform: str
    architecture: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class RootAuthority:
    root_id: str
    root_public_key: bytes
    epoch: int
    version: int
    app_id: str
    channel: str
    source_repo: str
    workflow: str
    minimum_release_sequence: int
    signers: tuple[AuthoritySigner, ...]
    revoked_key_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class ReleaseApproval:
    """Validated authorizations, not an OS-enforced install capability."""
    release: gate.VerifiedMetadata
    root_id: str
    root_epoch: int
    root_version: int
    builder_id: str
    build_id: str
    run_id: str
    source_repo: str
    workflow: str


def _parse_root(raw):
    p = _decode(raw, ROOT_FIELDS, MAX_POLICY)
    if (p["schema"] != 1 or type(p["schema"]) is not int
            or not _text(p["root_id"]) or not _integer(p["epoch"], minimum=1)
            or not _integer(p["version"], minimum=1)
            or not _integer(p["expires_at"], minimum=1)
            or p["app_id"] != gate.APP_ID or p["channel"] != gate.CHANNEL
            or p["source_repo"] != SOURCE
            or not _text(p["workflow"])
            or not _integer(p["minimum_release_sequence"], minimum=0)
            or type(p["signers"]) is not list
            or not 1 <= len(p["signers"]) <= 12
            or type(p["revoked_key_ids"]) is not list
            or len(p["revoked_key_ids"]) > 24):
        deny("Invalid root policy fields")
    pub = _public(p["root_public_key"])
    revoked = p["revoked_key_ids"]
    if any(not _text(x) for x in revoked) or revoked != sorted(set(revoked)):
        deny("Invalid root signed revocation set")
    signers = []
    keys = set()
    roles = set()
    for rule in p["signers"]:
        if type(rule) is not dict or set(rule) != SIGNER_FIELDS:
            deny("Unexpected or incomplete signer authorization")
        if (not _text(rule["key_id"]) or rule["key_id"] in keys
                or rule["key_id"] in revoked
                or rule["role"] not in ("release", "builder")
                or type(rule["role"]) is not str
                or rule["platform"] != "linux"
                or rule["architecture"] != "x86_64"
                or not _integer(rule["expires_at"], minimum=1)):
            deny("Malformed, duplicated or revoked signer role")
        keys.add(rule["key_id"])
        roles.add(rule["role"])
        signers.append(AuthoritySigner(
            rule["key_id"], _public(rule["public_key"]),
            rule["role"], rule["platform"], rule["architecture"],
            rule["expires_at"]))
    if roles != {"release", "builder"}:
        deny("Root lacks separate release and builder authorities")
    return p, pub, tuple(signers), frozenset(revoked)


def verify_root_policy(root_raw, root_sig, anchor, *, now):
    """Verify policy ONLY against a root pin independently provided by caller."""
    gate._require_ci()
    if (type(anchor) is not RootAnchor
            or not _text(anchor.root_id)
            or type(anchor.public_key) is not bytes or len(anchor.public_key) != 32
            or not _integer(anchor.minimum_epoch, minimum=1)
            or not _integer(anchor.minimum_version, minimum=1)
            or type(now) is not int):
        deny("Missing independently authenticated trusted root anchor/policy")
    policy, public, signers, revoked = _parse_root(root_raw)
    if (policy["root_id"] != anchor.root_id
            or policy["epoch"] < anchor.minimum_epoch
            or policy["version"] < anchor.minimum_version
            or public != anchor.public_key):
        deny("Wrong root identity, rollback, or unpinned root key")
    _signature(anchor.public_key, root_sig, ROOT_DOMAIN, root_raw)
    if policy["expires_at"] < now:
        deny("Root policy expired according to externally trusted time")
    return RootAuthority(
        policy["root_id"], public, policy["epoch"], policy["version"],
        policy["app_id"], policy["channel"], policy["source_repo"],
        policy["workflow"], policy["minimum_release_sequence"],
        signers, revoked)


def rotate_root_anchor(anchor, rotated_raw, old_sig, new_sig, *, now):
    """Dual-sign root change. Persisting the resulting pin is OUT OF SCOPE.

    Require the installed old root's signature and candidate new root's
    signature over the SAME canonical policy, advancing epoch AND version
    by exactly 1. The new root is untrusted until old authority authorizes it.
    """
    gate._require_ci()
    if type(anchor) is not RootAnchor:
        deny("Independently installed previous root is required")
    p, candidate, _, _ = _parse_root(rotated_raw)
    if (p["root_id"] != anchor.root_id
            or p["epoch"] != anchor.minimum_epoch + 1
            or p["version"] != anchor.minimum_version + 1
            or candidate == anchor.public_key
            or p["expires_at"] < now):
        deny("Root rotation violates signed old-root epoch/version policy")
    _signature(anchor.public_key, old_sig, ROOT_DOMAIN, rotated_raw)
    _signature(candidate, new_sig, ROOT_DOMAIN, rotated_raw)
    new_anchor = RootAnchor(anchor.root_id, candidate,
                            p["epoch"], p["version"])
    verify_root_policy(rotated_raw, new_sig, new_anchor, now=now)
    return new_anchor


def _select(authority, key_id, role, platform, arch, now):
    if key_id in authority.revoked_key_ids:
        deny("Signer is explicitly revoked")
    matches = [s for s in authority.signers if s.key_id == key_id]
    if len(matches) != 1:
        deny("Signer lacks root-authorized key identity")
    signer = matches[0]
    if (signer.role != role or signer.platform != platform
            or signer.architecture != arch or signer.expires_at < now):
        deny("Signer lacks requested role/platform or is expired")
    return signer.public_key


def verify_release_provenance(root_raw, root_sig, anchor,
                              release_raw, release_sig,
                              attestation_raw, attestation_sig,
                              *, platform, architecture,
                              minimum_sequence, now):
    """Two distinct root-authorized signers bind release bytes + provenance.

    Signature on source-commit label alone does not prove a build is honest.
    CI attestation signing is simulated and real builder source identity is
    not authenticated outside this synthetic fixture.
    """
    root = verify_root_policy(root_raw, root_sig, anchor, now=now)
    if (platform != "linux" or architecture != "x86_64"
            or type(minimum_sequence) is not int or minimum_sequence < 0):
        deny("Unsupported or untrusted release platform / sequence policy")
    att = _decode(attestation_raw, ATTEST_FIELDS, MAX_ATTEST)
    release_key_id = _decode(release_raw, gate.FIELDS, gate.MAX_META)["key_id"]
    if type(release_key_id) is not str:
        deny("Invalid release key ID")
    release_key = _select(root, release_key_id, "release",
                          platform, architecture, now)
    try:
        release = gate.verify_metadata(
            release_raw, release_sig,
            {release_key_id: release_key},
            expected_platform=platform, expected_arch=architecture,
            minimum_sequence=max(minimum_sequence,
                                 root.minimum_release_sequence), now=now)
    except gate.TrustRejected as exc:
        deny("Root-authorized release signature/policy rejected: " + str(exc))
    if (att["schema"] != 1 or type(att["schema"]) is not int
            or any(type(att[k]) is not str for k in
                   ("builder_id", "source_repo", "source_commit", "workflow",
                    "run_id", "build_id", "app_id", "channel", "platform",
                    "architecture", "artifact_name", "artifact_sha256"))
            or any(type(att[k]) is not int for k in
                   ("artifact_size", "release_sequence", "issued_at", "expires_at"))
            or not _text(att["builder_id"]) or not _text(att["run_id"])
            or not _text(att["build_id"])
            or att["source_repo"] != root.source_repo
            or att["workflow"] != root.workflow
            or att["app_id"] != root.app_id or att["channel"] != root.channel
            or att["platform"] != platform or att["architecture"] != architecture
            or att["issued_at"] > now or att["expires_at"] < now
            or att["expires_at"] <= att["issued_at"]
            or att["expires_at"] - att["issued_at"] > MAX_LIFETIME):
        deny("Untrusted build provenance identity or freshness")
    builder_key = _select(root, att["builder_id"], "builder",
                          platform, architecture, now)
    if att["builder_id"] == release.key_id:
        deny("Release signer cannot self-attest the build")
    _signature(builder_key, attestation_sig, BUILD_DOMAIN, attestation_raw)
    pairs = (
        ("source_commit", release.source_commit),
        ("artifact_name", release.artifact_name),
        ("artifact_sha256", release.artifact_sha256),
        ("artifact_size", release.artifact_size),
        ("release_sequence", release.sequence),
    )
    if any(att[k] != v for k, v in pairs):
        deny("Builder attestation does not bind exact signed release bytes")
    return ReleaseApproval(
        release, root.root_id, root.epoch, root.version, att["builder_id"],
        att["build_id"], att["run_id"], root.source_repo, root.workflow)


def verify_provenance_and_seal(source, root_raw, root_sig, anchor,
                               release_raw, release_sig,
                               attestation_raw, attestation_sig,
                               *, minimum_sequence, now):
    """CI-only authority-chain gate -> existing one-FD sealed-byte pipeline."""
    approval = verify_release_provenance(
        root_raw, root_sig, anchor, release_raw, release_sig,
        attestation_raw, attestation_sig, platform="linux",
        architecture="x86_64", minimum_sequence=minimum_sequence, now=now)
    root = verify_root_policy(root_raw, root_sig, anchor, now=now)
    signer_key = _select(root, approval.release.key_id, "release",
                         "linux", "x86_64", now)
    # Existing verifier independently rechecks release signature and copies
    # exactly these signed bytes. No provenance-free fallback or pathname
    # reopening after the original source FD is pinned.
    return gate.verify_and_seal(
        source, release_raw, release_sig, {approval.release.key_id: signer_key},
        expected_platform="linux", expected_arch="x86_64",
        minimum_sequence=max(minimum_sequence,
                             root.minimum_release_sequence), now=now)
