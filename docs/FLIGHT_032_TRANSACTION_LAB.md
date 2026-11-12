# Flight Radar 0.3.2.dev4 — Phase B transaction laboratory (CI only)

**NOT A USER INSTALLER. No production install CLI is provided.** The only CLI command is `python3 tools/flight_transaction_lab.py --plan`, which writes nothing and requires no privileges.

## Purpose

Provide testable, versioned building blocks for a future **distinct-name** side-by-side installation of the security candidate, while preserving the original user's pipx 0.3.2.dev4 installation, v0.3.1 archive, settings, old sudoers and readsb/tar1090 services.

`TransactionLab` is gated to GitHub Actions with `CI=true` and an exact `RUNNER_TEMP/flight-transaction-lab/<fixture>` root. It only works on arbitrary small test bytes and **never invokes pip, Python package installers, sudo, systemctl, Qt or SDR processes**. The laboratory is not a model of a byte-exact installed wheel.

Phase-B safeguards tested:
- Non-overwrite versioned fixture staging, hash/ownership/size validation, collision refusal.
- Atomic `current` link replacement using same-directory symlink + rename.
- Write-ahead journal and explicit recovery after injected failure at journal, pointer and state transitions.
- Two preserved release payloads through switching, rollback and deactivation; no release deletion.
- Refusal of symlinked roots, corrupted fixture, wrong owner and a non-disposable path.
- Verify fake installed pipx owner file remains untouched.

**Remaining HOLD:** independent concurrency and symlink-race review, actual application package/venv/wheel-hash locking, reliable installer rollback/uninstall when deletion fails, service lifetime policy and USB exclusive ownership, real Pop!_OS COSMIC QA, licensing, binary artifact signing, package-native launch behavior. Old `/etc/sudoers.d/tihulu-flight-radar` rule confirmed by owner remains untouched and requires separate authorized review.

The history of original sources is unchanged: PR #22 0.3.1, PR #23 original 0.3.2.dev4 and PR #25 security candidate. This stacked PR must stay Draft. No merge or release without separate independent validation and the owner's explicit approval.

## Agent 07 hardening (separate Draft PR stacked on PR #28)

- Linux-only, file-descriptor-anchored fixture transaction path operations; refuse
  symlink ancestors, foreign owners, and group/other writable laboratory roots.
- Distinct release paths use `RENAME_NOREPLACE`; pointer and state changes use
  `RENAME_EXCHANGE` followed by **expected inode and content checks**.
  If a race is detected, exchange back and preserve pending transaction evidence.
  A raced foreign entry must not be unconditionally replaced or unlinked.
- Journal `before` schema, expected owner, names, and relevant release artifacts
  are checked **before** attempting recovery. Recovery checks only expected
  before/after state and pointer transition combinations, and keeps pending
  evidence until the restored state passes consistency validation.
- Rollback selects the prior release and commits it within a single flock.
- Journal/pointer/state/stage transitions fsync relevant directory descriptors.
  Crashed staging directories are not silently deleted: later stage attempts
  refuse the unresolved orphan and retain evidence.
- Linux CI exercises controlled foreign-file races, journal corruption,
  multi-process lock serialization, a sudden child-process termination after
  pointer replacement, directory-fsync presence and fake-user preservation.
- Windows and macOS collect the full Python suite but skip only explicitly
  Linux-only transaction fixture tests; Linux executes them without skips.
- RF history: second position updates at a different location and the same
  millisecond are retained; a deterministic mock-clock regression is provided.

**Do not overstate:** This remains a synthetic CI laboratory. An attacker
with the same UID can mutate owner-writable paths, the CI flags are forgeable,
the manifest's public SHA-256/OWNER tuple is not trusted release provenance,
and a directory fsync presence test is not proof of resilience to real power
loss on every filesystem. The pointer protocol is not validated for running
applications, active launchers, wheel environments, or physical SDR. Failure
of any rollback/restore retains HOLD. Real installer/uninstaller, service
lifetime, sudoers policy, physical machine validation, package signing and
release approval stay **HOLD**. Independent Agent 06 exact-head review is
required; do not merge or deploy this Draft PR.


## Agent 07 PR #30 follow-up — retained-evidence race hardening (new Draft only)

This isolated follow-up is stacked on Agent 06 independent audit-only Draft PR #30,
not on a deployed application. Its threat model **does not claim any absolute
same-UID adversary resistance**: a malicious same-account process can rewrite an
owner-controlled directory, create or remove entries, swap trusted paths, and
forge the public OWNER/sha256 metadata. A full non-deletion guarantee against
such an actor is impossible if the actor controls the mutable namespace.
Production remains HOLD until a stronger privileged/trusted-path boundary and
authenticated artifacts are architected, tested, and independently approved.

- **No automated pathname unlink** remains in the transaction laboratory.
  After RENAME_EXCHANGE, displaced state/pointer data stays at a distinct
  `.tx-*` or `.pointer-*` quarantine name. Deactivation retains
  `.retired-*`; successful journal finalization retains
  `.retired-journal-*` evidence. Failed temporary paths remain for manual
  review as well. If another same-UID writer races with those names, no
  check-then-unlink code can destroy their newly substituted bytes.
  The program does not recursively clean any external path.
- **Bounded retention:** when retained slots reach 256, a new switch or
  rollback fails closed with an explicit manual-review error; entries are
  never silently deleted. Until a privileged and verified cleanup policy is
  designed, this deliberate conservative strategy can accumulate a small
  amount of metadata and impede transactions.
- **Immutable constructor root:** `locked()` uses the original validated
  base path and fails if RUNNER_TEMP changes. Base and root inode
  fingerprints are checked against the constructor/first-open values;
  ancestor links are refused by descriptor-relative opens.
- **Layered, cooperative lock:** a flock on the original RUNNER_TEMP
  *directory descriptor* spans the full critical section, including
  rollback target selection, while the existing lab.lock flock remains.
  Replacing only lab.lock no longer creates parallel critical sections
  when the base directory is unchanged. Revalidation after the operation
  raises on lock path replacement (without trying to delete foreign
  entries). Renaming/replacing the base directory itself is **not** solved
  against a malicious same-UID process; a genuine trusted anchor is still
  a production release blocker.
- Independent PR #30's former six deliberately vulnerable-behavior
  assertions were turned into **negative acceptance tests** in the new
  follow-up branch. These require no path-unlink, retained journal/state
  evidence, rejection of RUNNER_TEMP drift, and no overlapping critical
  section after lab.lock replacement. Corrupt journal and two-process
  cooperative rollback controls remain.
- Old-source scope is unchanged; no owner machine, pipx, legacy v0.3.1,
  QSettings, sudoers, readsb/tar1090, SDR, or live installation is accessed.
  CI workflow flags may be spoofed and are **not** production authorization.

**Still HOLD:** independent Agent 06 re-review of this exact branch SHA,
same-UID hostile replacement of parent/root directories, production release
provenance/signature, actual side-by-side installation/uninstall, power-loss
atomicity, and real hardware/service isolation. Green synthetic CI does
not waive any of these gates.


## Agent 07 continuation on Agent 06 PR #32: P1/P2 containment and source trust

**Scope:** Synthetic Linux-only fixture transaction laboratory. The original
PR #32 independent QA branch remains frozen. This new stacked Draft changes
no production installer, application, sudoers, user files or SDR/services.

### P1-F31-01 — detached root must not report success

On entering a transaction, descriptor-bound root, parent and base identities
are checked. On leaving the `locked()` context, including when the body raises,
the *currently reachable* base pathname, parent entry and root entry are
recompared against the held descriptors while locks are still held. A
root-directory rename followed by creating a new directory at the original
path now returns an explicit `Fixture root namespace changed during transaction`
error rather than reporting a successful switch. Committed bytes in the
displaced original directory are **retained**. A caller must treat a failed
operation as an indeterminate transaction and inspect the preserved journal
before attempting recovery. This is detection, **not rollback or protection**
against same-UID hostile namespace manipulation.

### P1-F31-02 — cooperating base-directory flock split

The CI-only laboratory now takes a flock on the root-owned filesystem root
directory descriptor `/` before taking the original RUNNER_TEMP directory
flock and inner `lab.lock`. This stable shared **cooperative** anchor prevents
two compliant laboratory clients from taking independent locks on separately
replaced RUNNER_TEMP base inodes, provided they run in the same mounted
filesystem/root namespace. A hostile same-UID process may ignore advisory
flock, or manipulate mount namespaces when permitted. The broad root-directory
lock is an intentionally conservative *disposable test technique*, not an
approved production locking protocol. No production installer should adopt
global `/` locking.

### P1-F31-03 — verified-origin design versus self-hash

The public `owner` field and SHA-256 hash embedded inside `manifest.json`
are **content self-consistency only**. Neither field certifies who published the
payload. The lab supports an **optional immutable per-instance external
`external_pins={"release_name": "64lowercasehexdigest"}` registry**, copied
from the caller rather than loaded from the mutable release tree. When a
test supplies this pin, a self-consistent but altered payload is rejected
before activation, and missing pins fail closed. A test also confirms the
legacy unpinned *CI-only* fixture can still accept the forged self-hash.

This registry does **not** implement authenticated provenance: a malicious
same-UID process may control the caller, code, environment or pin source.
A real production path needs a separately reviewed trust bootstrap:

1. Reproducible/build-identity inventory and release manifest containing
   exact artifact SHA-256, length, platform, architecture, version, signing key
   identifier and protected source commit/build-attestation references.
2. Canonical signed metadata and Ed25519 (or equivalent audited) detached
   signatures, verified **offline** against a versioned pinned trusted keyring
   distributed through an independently authenticated channel. The signer
   private key must never reside in the repository, owner-writable
   installation root, CI fixture or downloadable artifact bundle.
3. Fail-closed checks for unknown/revoked signer, expired or rollbacked
   metadata, unapproved artifact name, hash/size disagreement, bad signature,
   replay and key rotation. A signature downloaded from the same untrusted
   location without a separately anchored public key provides no origin proof.
4. Verify bytes obtained under a trusted acquisition boundary and transfer
   them to installation without re-opening an attacker-writable path. Record
   digest and metadata identity in the transaction journal; independently
   security-review the entire installer and failure/recovery boundaries.

**None of these signature / trust-bootstrap / real artifact operations has
been implemented in this lab. Real package provenance: P1 HOLD.**

### P2-F31-04 — quarantine accounting

For every switch or rollback, reserve four potential retained names **before
writing the pending journal**. Each temporary state/pointer/retirement step
checks its own remaining slot before creating or renaming entries. Recovery
also reserves headroom before changing state. Exactly 255 retained names
blocks a new switch without creating a journal; 252 may complete a
representative transaction without exceeding 256. No file is deleted to
satisfy the bound; manual evidence inspection remains required. Concurrent
uncooperative same-UID writers may still add new entries; 256 is a
**cooperative laboratory bound**, not a filesystem-wide quota.

### QA and independent approval

Agent 06's original PR #32 tests intentionally **passed when P1/P2 weaknesses
were reproduced**. The new Draft's tests invert those into fail-closed
acceptance assertions for root replacement, directory-lock overlap and cap
accounting. The public-manifest forgery reproduction is **retained** as a
deliberate HOLD; separate tests verify a caller-provided pin rejects that
mutation. Prior foreign-entry retention, corrupt journal, rollback and
cross-platform CI remain required.

**HOLD:** adversarial same-UID arbitrary manipulation, process control or
mount/root namespace changes; physical power loss and actual installed
application rollback; fully authenticated signatures and source trust;
genuine user-host interactions with pipx/v0.3.1, QSettings/XDG, sudoers,
readsb/tar1090 and SDR. Independent Agent 06 exact-HEAD re-review required.
No merge, installation or public release authorization.
