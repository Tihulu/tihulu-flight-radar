# Flight Radar — PR #44 key-material revocation continuity (CI-only)

**PUBLIC RELEASE HOLD**. Isolated remediation Draft stacked **directly on
frozen development PR #44 SHA `ea67f3f679adc813ae84193307d4b253f42d8fd7`**,
NOT on independently authored PR #45/#46/#47. Those original branches,
independent attack proofs, production application and the owner's PC remain
untouched. No production signing key is used or created.

## Two original independent P2 attacks

- **P2-F44-01 — builder material alias:** frozen independent QA PR #46
  `test_30_POSITIVE_GAP...` proves an authenticated OLD policy that
  revoked `builder1`, but authorized `builder2`, can be followed by a
  validly old+new signed policy allowing `builder3` using the identical
  Ed25519 public/private key material of retired `builder1`. The old
  revocation ID remains intact; ID-only checks miss the resurrected key.
- **P2-F44-02 — root material alias:** frozen PR #46
  `test_31_POSITIVE_GAP...` proves retirement of `root1` by ID while
  `root4` reuses exactly `root1` public bytes; valid old/new 2-of-3
  signatures could misleadingly count it as a new root identity.

**Remediation:** root-policy canonical signed JSON now contains both
`revoked_key_ids` and **`revoked_key_fingerprints`**, an exact ID → SHA-256
of Ed25519 public key bytes tombstone mapping. The fingerprint uses a
domain-separated, null-terminated
`TIHULU_FLIGHT_ED25519_KEY_TOMBSTONE_V1` prefix and the exact 32 public
bytes (never private keys). Both fields are mandatory and signed by the
existing 2-of-3 OLD+NEW root quorum during rotations, and by the
independently pinned 2-of-3 bootstrap quorum for the initial fixture.

`RootAuthority` stores an immutable mapping-proxy copy of this trusted
fingerprint history, beside the frozen key-ID ledger. During each
authenticated transition, the verifier requires:

1. The signed fingerprint map's key set matches *exactly* the sorted
   revoked IDs; every digest is canonical lowercase 64-hex, and all
   values are unique.
2. Every previously authenticated retired ID and its fingerprint remains
   unchanged (**monotonic, no clearing, replacing or reassigning a prior
   tombstone**). This includes tombstones from all earlier epochs carried
   through the authenticated immutable prior-root chain.
3. Every ID removed from the authenticated previous ROOT/SOURCE/BUILDER/
   RELEASE roster appears in the new revoked-ID list with the **actual
   SHA-256 fingerprint of its previous authenticated public key bytes**.
   The candidate cannot substitute a false fingerprint for its own retired
   key.
4. No currently active ROOT/SOURCE/BUILDER/RELEASE key material may have
   a fingerprint in the signed accumulated tombstones, **regardless of
   key ID or role**. New names do not revive old keys.
5. Legitimate 2-of-3 OLD and 2-of-3 NEW Ed25519 signatures still both
   required over identical canonical policy bytes; threshold counting is
   by **distinct Ed25519 public key material**, not just IDs. Valid new
   keys, proper retirement and authorized rotations keep passing.

**Important migration limitation:** this strictly extends the synthetic
root-policy signed schema. Earlier unsupplemented CI manifests are
deliberately rejected; there are no production manifests to migrate here.
Production schema negotiation/migration and authenticated recovery from
legacy roots need a separately authorized review. If a root signs an
untrue fingerprint for an already previously revoked, no-longer-active key
during FIRST bootstrap, the fixture can verify the root's signed claim but
cannot prove that historical fingerprint was authentic from an external
audit. A real bootstrap must establish its entire historical revocation
inventory through a separately authenticated channel; this remains
**P1-ROOT HOLD**.

## Test preservation and independent evidence

- The original PR #44 author's **34 tests remain**; only fixtures are
  extended with the new signed mapping of known test key material.
  All original assertions and old 2-of-3/rotation/source/build/release
  behaviors remain in place.
- Frozen independent PR #46 itself stays untouched, retaining original
  **positive** exploit witnesses #30 and #31 and independent strict
  negatives #11 and #12. A *copy* of that 31-case source is added on this
  separate branch as `tools/flight_pr44_key_material_qa_derived.py`:
  #30 and #31 become strict **negative** controls with the same actual
  revoked key aliases and signed old+new quorums explicitly checked first.
  New #32–34 test missing/forged fingerprints, authenticated third-epoch
  tombstone persistence and **builder → source** alias rejection.
- CI-only GitHub runner, `cryptography==46.0.3`, in-memory ephemeral
  Ed25519 test keys. No real/owner signing keys, bootstrap or installer.

## P0 / P1 / P2 safety boundaries

| Surface | CI decision | Production state |
|---|---|---|
| P2-F44-01 revoked builder fingerprint under fresh ID | PASS only if independent-derived *negative* test rejects despite valid quorums | Agent 06 re-review PENDING |
| P2-F44-02 revoked old root under fresh root ID | PASS only if negative test rejects despite valid quorums | Agent 06 re-review PENDING |
| Revocation historical monotonicity across roles and epochs | Synthetic signed state and immutable RootAuthority | Persistently authenticated OS-side state still absent |
| Original 2-of-3 and legitimate rotation | Preserve old assertions, verify exact-head CI | Root signing authority not provisioned |
| **P1-ROOT / PROVENANCE** | Synthetic root pin and signed policy | **HOLD** actual authenticated offline root bootstrap, real key custody/rotation/revocation freshness, verified source/build execution |
| **P1-BROKER / SAME-UID** | Not implemented | **HOLD** OS protected installer executable, release tree, activation pointer, trusted keyring, journal and FD broker; historical same-UID/FD races |
| **P1-ROLLBACK / FRESHNESS** | Root version floor and time supplied by CI caller | **HOLD** durable OS-protected monotonic history, trusted clock/revocation delivery, recovery and anti-replay |
| Real installer/uninstall, native macOS/Windows protected handles, physical SDR/services | Not implemented/tested | **HOLD** |

The signed fingerprint mapping is **authenticated in the test fixture** by
a previous valid root plus correct old/new quorum; the verifier is NOT a
trusted owner-independent persistent database. `RootAuthority` is a frozen
Python object, not a malicious same-process access control. A hostile same
process can manipulate private Python fields and OS file descriptors, and
authorized but compromised root quorum signers can deliberately approve
incorrect release/source/build claims. This is not an Ed25519 breach;
production key custody, trusted provisioning and separate builder
attestation must be independently authorized.

Do not touch existing Flight Radar 0.3.2.dev4, archived 0.3.1, pipx,
QSettings/XDG, sudoers, readsb/tar1090 or SDR. No real signing key,
user-machine action, merge, install, uninstall or release. **PUBLIC
RELEASE HOLD.**
