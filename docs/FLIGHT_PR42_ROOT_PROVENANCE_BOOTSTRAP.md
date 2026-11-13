# Flight Radar — P1-ROOT/PROVENANCE, independently authenticated bootstrap plan

**Status: ARCHITECTURE + CI-only executable prototype. PUBLIC RELEASE HOLD.**
This is not a production root of trust, a real signing or distribution
system, an installer, a verification credential provisioned on user devices,
or permission to modify any old Flight Radar release.

New isolated Draft stacked on Agent 06 frozen PR #42 exact
`324c267ca38ad15c176be243e21dd4477a5781cb`. All prior Drafts remain
open/unmerged and untouched. Existing v0.3.2.dev4, 0.3.1 archive, pipx,
QSettings/XDG, sudoers, readsb/tar1090, RTL-SDR and owner PC untouched.

## Trust chain and signed roles — what the CI fixture actually implements

`tools/flight_root_provenance_ci.py` verifies THREE independently signed
envelopes, but only with **ephemeral keys generated in GitHub-hosted CI RAM**:

```text
TRUSTED INSTALLER CONFIG / OUT-OF-BAND PIN [NOT IMPLEMENTED]
  root key fingerprint, key bytes, root ID, min root epoch/version
                      |
                      | Ed25519 ROOT_DOMAIN signature
                      v
CANONICAL ROOT POLICY (untrusted downloaded bytes)
  signed app/channel, source repo, build workflow, root pubkey,
  root epoch/version/expiry and minimum release sequence
  signer ID -> public key -> exactly one role -> platform/arch/expiry
  revoked key IDs (key removed from active signer roster)
                /                         \
               v                           v
RELEASE SIGNER (release role)      BUILDER SIGNER (builder role)
 Ed25519 DOMAIN signature          Ed25519 BUILD_DOMAIN signature
 canonical release manifest         canonical source-build attestation
 source commit, filename,           source repo, commit, builder ID,
 platform, arch, digest/size,       workflow, run/build IDs, platform,
 release sequence, expiry           digest/size, sequence/expiry
                \                         /
                 exact signed field equality
                          |
                          v
  Existing CI-only verify_and_seal() independently rechecks release
  signature, opens source pathname ONCE, hashes COPIED bytes,
  seals Linux memfd, and returns a verified-byte fixture.
```

The signed root policy is NEVER permitted to choose its own trusted root.
The caller must supply an independently authenticated `RootAnchor` public
key (including ID, minimum epoch/version). This code does **not** and
cannot prove that the caller obtained its pin by an authentic channel;
the synthetic tests generate pins in-memory, separately from untrusted
manifest input. A legitimate-looking key inside a download, README,
manifest, GitHub Actions output or the same unauthenticated artifact
channel is NOT bootstrapping a production root.

Strictly canonical JSON, no duplicate keys, unknown fields, nested
unreviewed signer structures or role confusion. Root may explicitly
authorize multiple release and builder signers by ID, public Ed25519
key, singular `release` / `builder` role, Linux-x86_64 platform
and expiration; wrong role, unknown ID, revoked signer, stale signer or
wrong channel is denied. The policy also pins an **exact source repository
and build workflow identity**. Builder attestations must be signed by a
separately root-authorized builder key; a self-reported `source_commit`
in an Ed25519-signed release alone is insufficient provenance. Exact
attestation/release source commit, filename, content digest, byte size
and sequence must agree, as must repository/workflow/app/channel/platform.

### Root/key rotation and revocation rules

- The current independently pinned root can authorize a **new** root
  only by signing the same canonical rotated policy that the **new** root
  also signs (cross-sign + self-sign). The CI primitive requires the same
  root ID, a changed key and exactly `+1` epoch and `+1` version
  from the CURRENT **caller-provided trusted pin**. It refuses forged
  old/new signatures, wrong key, stale root or expired root.
- After rotation, callers must **atomically commit the new public root
  pin and monotonic epoch/version** in storage unavailable to the hostile
  same-UID principal, before accepting further updates. This durable
  storage, fsync transaction, pin provisioning, offline rollback and
  recovery process are **NOT IMPLEMENTED** here. A peer can replay old
  root material when the external trusted anchor has not advanced.
- Root-signed `revoked_key_ids` denies those IDs, while the active
  signer allowlist must remove revoked IDs. Old release signatures
  using a revoked key are rejected. However **revocation freshness**
  cannot be guaranteed without an independent trusted update channel,
  root expiry/freshness validation and a persistently protected latest
  root version. This remains **P1 HOLD**.
- Ed25519 **private keys MUST NEVER** exist on user devices, in the repo,
  on generic release/test CI runners, in installer packages or logs.
  Proposed production signing uses separately operated, audited offline
  or hardware-backed custody with signer authorization, multi-party
  approval, issuance logs, rotation and emergency key compromise handling.
  No production signing key is generated, chosen or installed by this PR.

## Actual independent bootstrap — REQUIRED and NOT YET PROVEN

Owner-reviewed acceptance for each OS/distribution must specify
**which independent authenticated delivery channel** installs the initial
`root_id`, Ed25519 public bytes and fingerprint and how the channel is
verified against an independently published expected fingerprint. Candidate:

1. Offline installation media or an appropriately authenticated
   OS-package/vendor-owned channel delivers a small read-only trust
   bootstrap into a **broker-controlled** protected namespace. A root
   public key embedded in an owner-writable executable or downloaded
   JSON is NOT independent. Verify OS package signatures, fingerprint
   and provenance OUTSIDE the signed release channel.
2. Human approval of a separately conveyed root fingerprint, signed
   bootstrap inventory, approved roles, repository and official app ID.
   Document which humans are authorized, how the independently expected
   fingerprint is obtained, and how compromised devices/repositories
   are recovered. Do NOT assume GitHub repository write authority
   equals release signing authority.
3. Broker stores authenticated trusted root policy, epoch/version,
   latest release sequence, revocation state and keyring outside hostile
   same-UID write scope, with atomic journal+fsync and recovery.
4. Release/build signers emit canonical release manifest and an
   independently builder-signed provenance claim binding the **exact
   copied artifact bytes**. A signer-key signature on a free-form
   commit label or GitHub run ID does not verify source/build integrity.
5. Independent QA must demonstrate that a forged download-root,
   compromised test runner, untrusted repository change, revoked
   signer, root-key rollover, downgraded version, conflicting
   build attestation or owner-writable keyring CANNOT be accepted.
   Production authorization is HOLD until these are independently
   repeatable on isolated hardware/OS sandboxes.

**Important provenance scope:** the synthetic builder signature
proves possession of an authorized **test builder key** over the
attestation fields, not that a real builder executed the named workflow,
used the named source, or produced reproducible bits. Production provenance
needs authenticated builder identity, approved source-tree review,
SLSA/in-toto or equivalent signed provenance, builder isolation,
immutable workflow/ref, dependency/SBOM review, artifact retention
and optional independent rebuild comparison. Do not promote mutable
GitHub workflow identifiers or build logs into a trust root.

## Distinct production P1 HOLD categories (do not combine away)

| Area | Tested in this PR | Remaining production work |
|---|---|---|
| P1-ROOT/PROVENANCE | **SCOPED synthetic CI**: anchored Ed25519 root policy, role separation, root-signed revocation, dual rotation signature, release + builder-signed matching provenance, copied sealed bytes | **P1 HOLD:** owner-independent authenticated initial root bootstrap, real signing custody, revocation freshness, production source/build provenance and independent attestation |
| P1-BROKER/SAME-UID | Nothing beyond existing CI-only FD snapshot | **P1 HOLD:** OS-enforced installer/broker executable, keyring, owned release tree, activation pointer, journal, FD handoff and controls not writable by hostile same-UID processes; no `flock("/")` production shortcut |
| P1-ROLLBACK/FRESHNESS | Signed root/release version, expiry and caller-supplied sequence/time checked | **P1 HOLD:** independently protected, durable monotonic anti-rollback/anti-replay; trusted time or signed freshness, crash/power-failure/fsync and revocation freshness. Inputs `now` and `minimum_sequence` are currently caller supplied |
| Actual installer, uninstall, side-by-side migration | NONE | HOLD; owner approved staging and no collateral changes to legacy pipx, QSettings, sudoers, tar1090/readsb or SDR |
| Other OSes | Linux-only small CI memfd | HOLD; Windows/macOS protected handle transfer and OS trust equivalent need independent proof |

### Acceptance before moving beyond this CI prototype

A later independent Agent 06 review must verify exact SHA, signer-role
confusion, duplicated signer identities and overlapping keys, expired/
revoked signer and root, root rotation old+new signatures, absence of
self-authorized initial root, source/build mismatch attacks and the
fact that test ephemeral signing authority is **NOT** real. Separate
futures: broker privilege-boundary QA, OS trust bootstrap, persistent
anti-replay state, signed real build provenance, safe archive extraction
and crash recovery. Preserve complete prior Ed25519, FD and platform CI.

**P0/P1/P2 claims require exact-head CI and independent QA. PUBLIC RELEASE,
MERGE, INSTALL, UNINSTALL, OWNER WORKSTATION AND HARDWARE: HOLD.**
