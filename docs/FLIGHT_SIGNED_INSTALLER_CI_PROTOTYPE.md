# Flight Radar — CI-only signed artifact and sealed-FD trust prototype

**NOT an installer, updater, signer, deployer, releaser, or security
authorization. PUBLIC RELEASE HOLD.** This work is stacked on independent
Agent 06 audit-only PR #36; its findings and all older PRs stay unchanged.
Tests run only on a disposable GitHub-hosted Linux runner. No actual user
computer, current v0.3.2.dev4, original v0.3.1 archive, pipx, QSettings,
sudoers, readsb/tar1090, RTL-SDR or services are accessed.

## Implemented, limited test properties

- `tools/flight_signed_installer_ci_prototype.py` checks strict canonical
  UTF-8/ASCII JSON metadata and an Ed25519 detached signature with domain
  separation. Fields cover CI-specific application ID/channel, artifact
  basename, size, SHA-256 of the payload, platform, architecture, exact source
  commit, signing key ID, monotonic sequence, issue/expiry epochs and schema.
  Duplicated/unknown/noncanonical fields are denied.
- The trusted key registry is **provided independently by the caller**, not
  accepted from the package. Its test root is ephemeral and created anew in
  RAM by the CI test; the private key is NEVER persisted, printed, uploaded,
  embedded in fixtures or used to sign production bytes. Tests run against
  `cryptography==46.0.3` on the hosted runner. **This does not bootstrap
  production trust**. Anyone controlling the caller's root registry can
  impersonate the signer; owner-user same-UID processes remain a threat.
- Caller policy checks expected app/channel/platform/architecture,
  `minimum_sequence`, and a trusted current time. Monotonic state storage
  and root key rotation/revocation are NOT implemented. Tests simulate
  rollback/replay refusal only when a higher policy floor is passed in.
- After verifying **signed metadata** the runner opens a small file exactly
  ONCE via no-follow descriptor-relative path walking within `RUNNER_TEMP`.
  It validates regular-file/UID/mode/link-count/length constraints and
  copies bytes read from that *same open FD* into a new Linux
  `memfd_create(MFD_ALLOW_SEALING)`. SHA-256 is computed over the **copied
  bytes**, compared with the signed manifest and verified again from the
  sealed FD. `F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL` are
  required and verified. No pathname reopen to retrieve the validated
  payload, no silent unsealed staging fallback, no file extraction or
  executable invocation.
- A deterministic rename/swap test changes the source pathname after the
  FD is acquired: the sealed handoff continues to contain only the
  originally opened, signed fixture bytes. In-place tampering is rejected
  rather than silently accepted. Forged signatures, unsigned self-hash,
  wrong key, wrong platform/architecture/app/channel, rollback sequence,
  duplicate metadata keys, wrong digest/size, expired signatures,
  symlinks/hardlinks and source paths outside the CI root are negative
  controls. A direct attempted write to the sealed memfd must fail.

## Required real OS trust boundary (NOT implemented)

Same-UID hostile processes can edit user-writable install targets, inject
other files, change the installer's code/environment, redirect the public
launch path, interfere with a mutable caller trust registry, or reopen/
rewrite data unless the OS prevents it. An advisory flock on `/` (used
in an older synthetic lab) is **not** an acceptable production security
architecture.

For an actual authorization boundary, a separately reviewed, OS-enforced
**trusted broker/storage authority** must own both the destination tree
and its activation pointer under permissions unavailable to the attacker.
Its executable, policy, keyring, monotonic rollback state and journal must
also be outside the attacker's writable/control domain. A narrowly scoped
IPC API would accept only signer-authorized metadata and preverified sealed
FDs, authorize an exact app/platform/version/release target, and never
execute arbitrary installer hooks. If the threat model permits same-UID
control of this authority or of the OS kernel/mount namespace, **HOLD**;
no user-space check/recheck is sufficient.

A real installer would need a correctly authenticated, independently
distributed Ed25519 verification keyring, supply-chain attestations, trusted
anti-rollback state, key rotation/revocation, capability/drop-privileges
review, cross-platform equivalent FD isolation, sandboxed bounded archive
extraction, durable journal, crash/power-loss recovery, side-by-side legacy
release separation, uninstall proof of ownership, and offline-safe repair.
**None** of these is implemented by this CI-only prototype.

The sealed memfd freezes the **bytes handed off**, not the storage
namespace to which the installer may later write. The artifact's valid
signature says nothing about a compromised issuer or build pipeline.

## PASS/HOLD classification

| Property | Scope / verdict |
|---|---|
| Ephemeral test-root Ed25519 signature verified against independent caller-pinned public key | CI gate, PASS only when exact-head tests succeed |
| Canonical metadata, signed exact digest/size/app/platform/sequence/expiry checks | CI gate, PASS only when exact-head tests succeed |
| Single-open FD, copied-data digest, F_SEAL_* memfd handoff, hostile pathname swap | Linux synthetic CI gate, PASS only when exact-head tests succeed |
| Direct same-inode content rewrite after open | Synthetic CI fail-closed test; no hostile process-wide guarantee |
| Production signer custody, authentic key bootstrap, key revocation and monotonic state | **P1 HOLD** |
| Full real installer, owner-independent destination/activation trust boundary | **P1 HOLD** |
| Arbitrary same-UID process/namespace adversary, earlier final-check false-success | **P1 HOLD** (older race tests deliberately reproduce it) |
| Real wheel/package installation, sandboxed unpack, rollback/uninstall, power-loss durability | **HOLD** |
| Native Windows/macOS equivalent immutable-handoff policy | **HOLD**; GitHub native desktop CI tests do not exercise this Linux-only prototype |
| Owner host, legacy v0.3.1 / installed 0.3.2.dev4 / pipx / QSettings / sudoers / services / SDR | **HOLD / NOT TESTED** |
| Independent Agent 06 source-level security re-review | **REQUIRED / HOLD** |
| Merge, deployment, installation, public release | **HOLD** |

## Next review agenda

Agent 06 should audit exact SHA and independently challenge canonicalization,
signer/public-key trust source, rollback policy, signed-byte fidelity,
symlink/hardlink protection, partial writes, seal completeness, FD lifetime,
hostile same-UID changing in-place data during copy, and the fact that target
installation/storage is still unprotected. Add new test-only Draft PR if
needed. Do not merge old stacked audit/remediation Draft PRs or reuse CI test
keys in any real deployment.
