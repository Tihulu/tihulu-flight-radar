# Flight Radar — PR #38 signed metadata immutability and real-installer gates

**Scope: CI-only prototype. PUBLIC RELEASE HOLD.** This document specifies a
future security architecture and tests for independent review. It does not
authorize deployment, produce/retain a production signing private key, change
owner machines, or implement a real installer.

## P2-F37-01: completed synthetic interface remediation

The Ed25519 signature covers a strictly canonical, flat JSON envelope. Prior
to this change, the verifier returned a writable `dict` and `SealedFixture`
made another writable copy. A caller could change signed `platform`,
`sequence`, `architecture` and especially `artifact_size` after verifying
the signature. `read()` trusted that mutable length and could silently
return only a short prefix of the sealed file.

The CI-only verifier now returns an explicitly typed,
`@dataclass(frozen=True, slots=True)` `VerifiedMetadata`. This object
implements the read-only Mapping interface to retain existing
`metadata["field"]` consumers and rejects ordinary field assignment and
mapping mutation. Its thirteen signed fields have strictly validated
scalar-only types; signed lists, dicts, nested extension fields, duplicate or
unexpected fields fail closed **before** construction. No references to the
mutable JSON parser dict or original caller fields are kept. Consumers may
request `to_dict()` or `metadata_copy()`: these allocate new mutable
dictionaries, **never used as a trusted authorization source**. A caller can
modify the returned copies, but not the signed policy snapshot.

`SealedFixture` is also a frozen, slotted record (with a controlled internal
FD-close transition). The verified length is a separate immutable value
recorded from the actual successfully sealed and digest-verified copied
bytes, not from a writable downstream metadata dictionary. `read()`
checks the FD's size against this fixed length, issues a single positional
read of exactly that amount, and refuses short reads. Ed25519 validation,
original source-FD acquisition, hash checks and `F_SEAL_*` invariants
continue unchanged.

**IMPORTANT boundary:** Python `frozen=True` defends normal accidental or
unauthorized API assignments, **not hostile code executing within the
trusted interpreter**; low-level `object.__setattr__`, monkeypatching,
process memory control or code modification can bypass language immutability.
This is not an OS security primitive or a trusted production broker.
A malicious same-UID process that controls installer code/destination remains
a separate unaddressed P1.

## Concrete test acceptance

Preserve original PR #37 author's 22 tests (signature/key forgery, canonical
metadata, app/platform/arch, rollback floor/expiry, source swap, same-inode
tamper, hardlink/symlink, sealed-FD write attempt) and the original Agent 06
PR #38 independent controls. Only in this NEW branch, convert Agent 06's
`test_18` *positive P2 vulnerability reproduction* into a **negative**
assertion that policy fields/length cannot be reassigned. Additional tests
try signed nested JSON, mutations of caller-owned source dictionaries,
writable exported copies including nested data injection, direct object and
mapping mutation, read-size manipulation, unexpected fields, and forced
mismatch between FD length and verified byte count.

A passing original audit-suite test that *intentionally demonstrates* an
unresolved production signer/time/caller-authority weakness remains labeled
as evidence of HOLD, not a security pass.

## Independent trust/authority matrix and production milestones

| Authority or trust surface | Current code | Production requirement / next deliverable |
|---|---|---|
| Ephemeral CI public-key registry | Caller-supplied in-memory test root; source bytes signed with disposable RAM-only Ed25519 key | **P1 HOLD.** Document offline signing-key custody with review threshold; independently authenticated, versioned read-only root keyring on installation device, **not fetched from the same artifact channel**. Independently audit key rotation, revocation, compromise recovery and offline operation |
| Authorized release metadata | Canonical signed test app/platform/arch/sha256/sequence/expiry/commit syntax; flat immutable snapshot | **P1 HOLD.** Package real signed build provenance/attestation and SBOM; verify actual source/build identity, artifact platform, release channel, license and artifact authorization. A 40-character source commit label alone is not provenance |
| Anti-rollback, replay, time | Caller passes `minimum_sequence` and `now` in CI; only compares them | **P1 HOLD.** Trustworthy monotonic sequence/epoch store owned by broker, authenticated durable journal, secure clock or signed freshness/expiry policy, rollback recovery, power-failure and replay tests. A forged caller floor/clock can defeat current test checks |
| Trusted installer executable and permissions | **NONE**; a Python CI module does not install or unpack | **P1 HOLD.** OS-enforced broker executable/code integrity, a dedicated privilege/capability boundary and independently trusted update authorization; least-privilege IPC accepting only allowlisted app/version/target, no arbitrary shell or hooks |
| Destination and activation pointer | **NONE**; sealed memfd protects only handed-off bytes | **P1 HOLD.** Release tree, activation pointer, locks, policy/keyring and state on storage writable by broker **but inaccessible to hostile same-UID applications**. Descriptor-relative no-follow staging, directory-fsync/atomic journal transitions, strict ownership and rollback/uninstall identity checks. Never copy production `flock("/")` from older experimental lab |
| Verified source acquisition | Linux single-open no-follow read, memfd copy + SHA-256 over copied bytes, `F_SEAL_WRITE/GROW/SHRINK/SEAL` | Harden against in-place writes and unsafe archives, size/resource exhaustions, source FD inheritance/leak, decompression bomb and hostile package structure. Pass only sealed FD to isolated extraction/verification, never reopen attacker-controlled source path |
| Linux, Windows, macOS and Pi parity | Prototype runs **Linux CI-only**; generic application build jobs do not exercise this gate natively on other OSes | Design Windows protected file handles/ACLs and native signature/immutable handle boundary, macOS code signing and protected sandbox/staging, Pi OS permissions, sandboxed extraction, platform-specific independent QA; do not infer parity from app builds |
| Crash/power loss, data preservation | Existing synthetic journal lab only | Crash matrix for every activation phase, SIGKILL/power interruption, fsync errors/disk full, authenticated journal recovery, no foreign-file deletion, protected quarantine cleanup, idempotent uninstall |
| Deployed old/current app and shared resources | **Not touched** | Owner-authorized acceptance preserving working 0.3.2.dev4, v0.3.1 archive, pipx/QSettings/XDG, sudoers, readsb/tar1090 and RTL-SDR hardware arbitration |

### Staged action gates

**Phase B (next, separate Draft):** independently authenticated trusted-root
bootstrapping, key lifecycle and signed *real build* provenance in CI using
test-only keys; independent Agent 06 denial tests for forged/rotated/revoked
roots, metadata downgrade and builds mislabelled by a valid signer.

**Phase C:** durable trusted replay/rollback state plus sealed-FD intake to a
non-installing sandbox; power-cut/crash and adversarial archive limits tested.

**Phase D:** isolated broker proof-of-concept with protection of both release
tree and activation pointer **against the defined hostile same-UID actor**.
Must demonstrate privilege/storage ownership controls independently of
Python `frozen`, namespace recheck, or `flock("/")`. Failing any requirement
leaves installer/deployment HOLD.

**Phase E:** explicit owner approval for physical machine and existing
application-preservation QA. **Phase F:** independent release/security QA,
SBOM/notices/redistribution review, and release authorization.

No preinstalled/legacy app, 0.3.1 archive, pipx, sudoers, QSettings/XDG,
readsb/tar1090, SDR or user workstation may be modified under this Draft.
Merge, install, uninstall and public release remain prohibited.
