# Flight Radar — signed, isolated side-by-side installer design (proposal only)

**Status: PUBLIC RELEASE HOLD.** This file is a concrete design brief, **not**
an implemented installer, a verified signing root or a release authorization.
It describes a future architecture for independent review. No application
installation, sudoers edit, service action, SDR access or owner workstation
operation is performed by this PR.

## Frozen assets and separate target

- Installed original Flight Radar `0.3.2.dev4`, historical `0.3.1` archive,
  pipx environment, current user settings, old sudoers rules and live
  readsb/tar1090/SDR ownership **remain untouched**.
- New candidate MUST have a distinct, owner-reviewed application ID and name;
  no reliance on rewriting the old launcher, app data or QSettings keys.
- Phase 0 is **evidence only** on GitHub-hosted disposable CI. Phase 1
  requires signed-release provenance and independent red-team review before
  even discussing a production installer.
- Authenticated origin, authorized rollout, writable-path containment and
  physical power-loss correctness are separate gates. None follows from
  `sha256(image.bin) == manifest.sha256`.

## 1. Release trust bootstrap — mandatory gate

Produce a canonical metadata envelope, with a specified format/schema and
canonicalization procedure. At minimum:

- App ID, platform, architecture, distribution channel, semantic version,
  exact source commit, immutable build provenance reference and build ID.
- For each allowed artifact: basename without traversal, SHA-256 digest,
  exact size, media type, target platform, and origin/build attestation.
- Signing key identity, schema version, sequence/epoch and expiry policy.
- Explicit previous-version and minimum-safe-version policy for rollback.

**Signature:** offline Ed25519 over the canonical envelope, with detached
signature and fixed trusted-key identifier. The installer must bootstrap
the trusted verification key or keyring via an **independent, authenticated
channel** (not the same owner-writable download or mutable in-release
manifest). Signing private keys do not reside on release runners, user
machines, source control or published binaries. Keys require generation,
review, rotation, compromise revocation and recovery procedures, all
tested in an isolated signing pipeline.

Verify the signature and exact artifact metadata **before** trusting any
payload. Reject unknown key, bad signature, stale schema, expired metadata,
wrong app/platform, rollback epoch, replayed sequence, wrong size or digest,
unsupported architecture, duplicate names or paths, and unapproved build
provenance. A signature does not imply that a compromised build pipeline is
safe. Supply-chain provenance must be reviewed separately. A public self-hash
is **never** considered source authentication.

**HOLD:** key custody and distribution, trust-root rotation, revocation
availability when offline, reproducible build and build-source attestation,
signed manifest verifier integration; none implemented.

## 2. Artifact acquisition and verified-byte handoff

Treat the downloaded artifact pathname, ZIP contents, manifests and
download directory as adversarial. Use `openat2` with
`RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS` or an equivalent audited descriptor-
relative walk. Require regular file, expected ownership/mode/link count,
sane length and non-expanding decompression bounds, and reject unexpected
children or symlink/hardlink escape. This is **not** an identity guarantee
against a hostile same-UID actor who controls the installer process.

**Critical non-TOCTOU rule:** hash and parse bytes from one opened
descriptor and **handoff exactly those bytes**, never reopen the
attacker-writable source path after validation. Proposed Linux sequence:

1. Obtain the signed authorization metadata from a separately trusted
   channel and verify it with an independently anchored public key.
2. Obtain an immutable byte representation from a read-only FD; copy
   exactly the expected number of bytes into a new `memfd_create` object
   with `MFD_ALLOW_SEALING` (or a trusted owner-inaccessible staging
   filesystem when memfd capacity is unsuitable).
3. Verify SHA-256 and length over the **copied** bytes and signature-bound
   manifest, not over the original path after the copy. Validate package
   structure and content limits from that *same* frozen representation.
4. Apply Linux `F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL`,
   verify those seals, and pass the sealed FD to the unpacker/installer.
   Never pass an untrusted pathname or silently fall back to opening it.
5. Extract only inside a trustworthy sandbox, with a strictly reviewed
   allowlist, no symlinks/hardlinks/devices, no archive traversal and no
   special executable hooks without authorization. Verify installed output
   digest and manifest after staging and before atomic activation.
6. Any failed verification: record a non-sensitive cause and stop; preserve
   forensic evidence. No partial public launcher change.

The current `_View.verified_bytes(name)` method is **CI-only**: it returns
an in-process immutable copy of the exact bytes originally verified,
preventing a subsequent disk path rewrite from mutating that Python
`bytes` object. The extra exit recheck detects the measured after-`finish`
attack interleaving, but does **not** guarantee later path immutability.
No sealed memfd, actual unpacker, signed verification or artifact execution
exists here. Trusted source-of-truth and same-UID process integrity remain
HOLD.

## 3. Installer isolation and transaction protocol

- Acquire a fixed-scope owner-independent cooperating lock for the candidate
  installation only. **Never reuse the CI laboratory's `flock("/")`**
  mechanism for production; global locking is not safe as a design.
- A same-UID malicious process can ignore a cooperating flock, swap owner-
  writable paths or trigger a rename/ABA between the final check and
  return. No finite sequence of `lstat`/reopens can solve this. Production
  guarantees require an **OS-enforced storage/privilege boundary** the
  adversary cannot modify and a reviewed authorization broker. Without
  such a boundary, security against a hostile same-UID actor stays HOLD.
- Trusted broker handles only narrowly authorized staging/activation
  operations, with absolute naming rules, no relative traversal, pinned
  FDs, verified signer/metadata, and no arbitrary shell commands.
  Evaluate whether the threat model permits a minimal user-owned installer;
  if not, **do not claim successful secure deployment**.
- Keep original and candidate releases side by side in distinct namespaces.
  Use no-follow descriptor-relative staging and `RENAME_NOREPLACE`,
  durable journal with before/after release identity, authenticated
  artifact metadata and fd-based rollback evidence. The activation point
  and all crash states must be specified.
- Atomic pointer replacement is a namespace operation; holding a directory
  FD does **not** prove the public pathname still references it or prevent
  a malicious same-UID writer from reverting or replacing it. A final
  pathname comparison is only best-effort detection.
- No cleanup of a just-verified user-writable path via `unlink`. Keep
  evidence bounded, validate any quarantine deletion through independently
  trusted ownership and explicit user-approved cleanup. Model disk-full,
  journal-corrupt, fsync-failed, process-killed and power-loss crashes.
- Rollback/uninstall must not touch the existing pipx deployment, original
  v0.3.1 archive, original launchers, old user files, current sudoers or
  shared readsb/tar1090 processes. Uninstall only by exact ownership
  inventory and proof; preserve everything else.

## 4. Staged independent acceptance gates

| Phase | Deliverable | Mandatory negative tests | Gate |
|---|---|---|---|
| A — current | Disposable namespace and verified-byte snapshot lab | after-exit rename race, after-finish mutation, old foreign-byte retention | Scoped CI PASS only |
| B — provenance | Offline signature verifier and trusted test keyring | signature forgery, stale/revoked key, wrong build, replay/rollback, hostile download path | Independent security QA HOLD |
| C — acquisition | Sealed-FD byte handoff, content limits, archive hardening | rewrite after read, rename/reopen, symlink/hardlink, zip slip, partial copy, decompression bomb | Independent security QA HOLD |
| D — installer | Distinct-name staged native package and rollback simulation | same-UID namespace escape, lock split, crash/power cut, foreign owner/pipx/sudoers preservation | Independent security QA HOLD |
| E — hardware | Owner-approved real host acceptance | 0.3.1/0.3.2.dev4 isolation, readsb/tar1090 ownership, RTL-SDR exclusivity, Pop!_OS startup, QSettings separation | Owner + QA HOLD |
| F — public | License/distribution and signed artifact release | SBOM/notices, optional AI model redistribution, cross-platform packaging, signatures and rollback | PUBLIC RELEASE HOLD |

No owner-machine action or real installer authority is conferred by any
green synthetic CI check. An independent Agent 06 P0/P1/P2 review is required
at this Draft's **exact HEAD** before moving to the next phase.
