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
