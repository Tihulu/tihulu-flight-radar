#!/usr/bin/env python3
"""CI-ONLY trust/byte-handoff fixture. NOT an installer or signer.

The caller supplies a trusted Ed25519 public key independent of the untrusted
artifact and signed metadata. All private test keys are generated only inside
ephemeral CI tests. No production keys, downloads, extraction, activation,
services or owner workstation operations exist in this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DOMAIN = b"TIHULU_FLIGHT_SIGNED_CI_FIXTURE_V1\0"
APP_ID = "tihulu-flight-radar-ci-fixture"
CHANNEL = "disposable-ci"
SCHEMA = 1
MAX_META = 4096
MAX_ARTIFACT = 1024 * 1024
MAX_VALIDITY = 14 * 86400
FIELDS = frozenset((
    "schema", "app_id", "channel", "platform", "architecture",
    "artifact_name", "artifact_size", "artifact_sha256", "sequence",
    "issued_at", "expires_at", "source_commit", "key_id",
))
NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,79}\Z")
KEY_ID = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class TrustRejected(RuntimeError):
    """Refuse unsigned, untrusted, malformed, or inconsistent fixture bytes."""


@dataclass(frozen=True, slots=True)
class VerifiedMetadata(Mapping):
    """Immutable, flat, typed snapshot of previously signature-verified policy.

    The public mapping interface preserves existing metadata["field"] uses;
    frozen fields and slots prevent ordinary mutation or dynamic extensions.
    There are no nested lists/dicts to retain as writable aliases. Deliberate
    low-level object.__setattr__ bypasses, caller-process compromise and
    untrusted production key distribution remain out of scope / HOLD.
    """
    schema: int
    app_id: str
    channel: str
    platform: str
    architecture: str
    artifact_name: str
    artifact_size: int
    artifact_sha256: str
    sequence: int
    issued_at: int
    expires_at: int
    source_commit: str
    key_id: str

    def __iter__(self):
        return iter(field.name for field in fields(self))

    def __len__(self):
        return len(FIELDS)

    def __getitem__(self, key):
        if key not in FIELDS:
            raise KeyError(key)
        return getattr(self, key)

    def to_dict(self):
        """New ordinary dict with independent immutable primitive values."""
        return {key: self[key] for key in self}


def reject(message):
    raise TrustRejected(message)


def canonical_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            reject("Duplicate signed metadata key")
        result[k] = v
    return result


def _require_ci():
    # Safety interlock for accidental invocation; environment variables are
    # NOT an authentication or isolation boundary against a same-UID attacker.
    if (sys.platform != "linux" or os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or not os.environ.get("RUNNER_TEMP")):
        reject("CI-only Linux ephemeral runner required")
    if not hasattr(os, "memfd_create"):
        reject("Sealable Linux memfd is required; no fallback")


def verify_metadata(raw, signature, trust_roots, *, expected_platform,
                    expected_arch, minimum_sequence, now):
    """Verify strict canonical signed metadata against a caller-pinned key."""
    _require_ci()
    if type(raw) is not bytes or not raw or len(raw) > MAX_META:
        reject("Invalid metadata length")
    if type(signature) is not bytes or len(signature) != 64:
        reject("Invalid Ed25519 signature length")
    if type(trust_roots) is not dict:
        reject("Independent trusted-key registry required")
    if (type(expected_platform) is not str or type(expected_arch) is not str
            or type(minimum_sequence) is not int or minimum_sequence < 0
            or type(now) is not int):
        reject("Invalid caller policy")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        reject("Invalid signed metadata JSON")
    if type(value) is not dict or set(value) != FIELDS:
        reject("Unexpected signed metadata fields")
    if canonical_bytes(value) != raw:
        reject("Metadata is not canonical")
    # Type checks must reject bool, which is a Python subclass of int.
    if (type(value["schema"]) is not int or value["schema"] != SCHEMA
            or type(value["artifact_size"]) is not int
            or not 0 < value["artifact_size"] <= MAX_ARTIFACT
            or any(type(value[k]) is not int for k in
                   ("sequence", "issued_at", "expires_at"))
            or any(type(value[k]) is not str for k in
                   ("app_id", "channel", "platform", "architecture",
                    "artifact_name", "artifact_sha256", "source_commit",
                    "key_id"))):
        reject("Invalid signed metadata schema/types")
    if (value["app_id"] != APP_ID or value["channel"] != CHANNEL
            or value["platform"] != expected_platform
            or value["architecture"] != expected_arch):
        reject("Wrong signed artifact app/channel/platform/architecture")
    name = value["artifact_name"]
    if (not NAME.fullmatch(name) or name in (".", "..")
            or ".." in name or "/" in name):
        reject("Untrusted signed artifact basename")
    if (not HEX64.fullmatch(value["artifact_sha256"])
            or not HEX40.fullmatch(value["source_commit"])):
        reject("Malformed artifact digest or source revision")
    if (value["sequence"] < minimum_sequence
            or value["sequence"] < 0):
        reject("Signed sequence rollback/replay denied by trusted policy")
    if (value["issued_at"] > now or value["expires_at"] < now
            or value["expires_at"] <= value["issued_at"]
            or value["expires_at"] - value["issued_at"] > MAX_VALIDITY):
        reject("Expired/future signed metadata")
    key_id = value["key_id"]
    if not KEY_ID.fullmatch(key_id):
        reject("Invalid signing key id")
    public = trust_roots.get(key_id)
    if type(public) is not bytes or len(public) != 32:
        reject("Unknown or invalid independently pinned signing key")
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, DOMAIN + raw)
    except (InvalidSignature, ValueError):
        reject("Ed25519 signature verification failed")
    # Create a detached typed record; never publish the mutable JSON parser
    # dict, even transiently, as downstream authorisation metadata.
    return VerifiedMetadata(**value)


def _open_source_once(source, runner):
    """Descriptor-relative, no-follow path walk restricted to disposable CI."""
    source = Path(source)
    runner = Path(runner)
    if (not source.is_absolute() or not runner.is_absolute()
            or any(part in (".", "..") for part in source.parts)
            or any(part in (".", "..") for part in runner.parts)
            or not source.is_relative_to(runner)
            or source == runner):
        reject("Source must be inside disposable RUNNER_TEMP")
    fd = os.open("/", DIR_FLAGS)
    try:
        for component in source.parts[1:-1]:
            newfd = os.open(component, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = newfd
        result = os.open(source.name,
                         os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=fd)
        return result
    finally:
        os.close(fd)


def _write_all(fd, data):
    position = 0
    while position < len(data):
        written = os.write(fd, data[position:])
        if written <= 0:
            reject("Sealed staging write failed")
        position += written


@dataclass(frozen=True, slots=True)
class SealedFixture:
    """Frozen verified-FD handle; close() is the only internal state change.

    Neither metadata nor the verified byte count can be reassigned through
    normal Python attribute writes. A hostile same-process user can bypass
    Python language immutability; this remains CI-only, NOT an OS trust wall.
    """
    _fd: int | None
    metadata: VerifiedMetadata
    _verified_length: int

    def __post_init__(self):
        if (type(self.metadata) is not VerifiedMetadata
                or type(self._verified_length) is not int
                or self._verified_length <= 0
                or self._verified_length != self.metadata.artifact_size):
            reject("Inconsistent immutable sealed fixture length/metadata")

    @property
    def fd(self):
        if self._fd is None:
            reject("Verified descriptor has been closed")
        return self._fd

    @property
    def verified_length(self):
        """Validated length of the copied, sealed bytes (not mutable metadata)."""
        return self._verified_length

    def metadata_copy(self):
        """Editable downstream *copy*, never used as an authorisation source."""
        return self.metadata.to_dict()

    def read(self):
        fd = self.fd
        # Bind reads to the verified byte count, not a user-editable
        # manifest mapping or a caller-controlled length argument.
        if os.fstat(fd).st_size != self._verified_length:
            reject("Sealed FD no longer matches verified length")
        raw = os.pread(fd, self._verified_length, 0)
        if len(raw) != self._verified_length:
            reject("Truncated sealed FD read")
        return raw

    def close(self):
        fd = self._fd
        if fd is not None:
            # Internal lifetime transition of this otherwise frozen record.
            object.__setattr__(self, "_fd", None)
            os.close(fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def verify_and_seal(source, metadata_bytes, signature, trusted_keys, *,
                    expected_platform="linux", expected_arch="x86_64",
                    minimum_sequence=0, now):
    """Verify signed origin; copy from ONE source FD; seal the verified copy.

    Source path is opened ONCE, never re-opened after verification. The hash
    covers data COPIED into the memfd; it is checked before and after sealing.
    The memfd prevents later edits to the handoff bytes, but NOT a hostile
    same-UID attacker changing unprotected target/installer namespaces.
    """
    _require_ci()
    metadata = verify_metadata(
        metadata_bytes, signature, trusted_keys,
        expected_platform=expected_platform, expected_arch=expected_arch,
        minimum_sequence=minimum_sequence, now=now)
    source = Path(source)
    if source.name != metadata["artifact_name"]:
        reject("Artifact filename does not match signed metadata")
    original_fd = None
    staged_fd = None
    try:
        original_fd = _open_source_once(source, os.environ["RUNNER_TEMP"])
        before = os.fstat(original_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid()
                or bool(before.st_mode & 0o022)
                or before.st_size != metadata["artifact_size"]):
            reject("Unsafe/foreign/incorrect-size source file")
        if not all(hasattr(fcntl, name) for name in
                   ("F_ADD_SEALS", "F_GET_SEALS", "F_SEAL_WRITE",
                    "F_SEAL_GROW", "F_SEAL_SHRINK", "F_SEAL_SEAL")):
            reject("Linux memfd sealing not supported")
        staged_fd = os.memfd_create(
            "tihulu-ci-verified-fixture",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        digest = hashlib.sha256()
        remaining = metadata["artifact_size"]
        while remaining:
            part = os.read(original_fd, min(65536, remaining))
            if not part:
                reject("Truncated artifact during single-FD copy")
            _write_all(staged_fd, part)
            digest.update(part)
            remaining -= len(part)
        if os.read(original_fd, 1):
            reject("Extra trailing bytes after signed artifact length")
        after = os.fstat(original_fd)
        if (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns):
            reject("Source mutated during verified copy")
        if digest.hexdigest() != metadata["artifact_sha256"]:
            reject("Copied artifact digest does not match signed digest")
        seals = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                 | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        fcntl.fcntl(staged_fd, fcntl.F_ADD_SEALS, seals)
        if fcntl.fcntl(staged_fd, fcntl.F_GET_SEALS) & seals != seals:
            reject("Sealed verified-FD flags missing")
        copied = os.pread(staged_fd, metadata["artifact_size"], 0)
        if hashlib.sha256(copied).hexdigest() != metadata["artifact_sha256"]:
            reject("Copied sealed artifact changed unexpectedly")
        # copied is read from the successfully sealed FD and its digest was
        # checked against the original Ed25519-authorised manifest above.
        # Freeze that verified length in the returned object.
        output = SealedFixture(staged_fd, metadata, len(copied))
        staged_fd = None
        return output
    finally:
        if original_fd is not None:
            os.close(original_fd)
        if staged_fd is not None:
            os.close(staged_fd)
