# Flight Radar — Agent 08 P1 broker OS-boundary remediation

**PUBLIC RELEASE HOLD — CI-ONLY REFERENCE, NOT DEPLOYMENT.** This Draft stacks exactly on frozen independent Agent 06 QA PR #50 SHA bd5c73ef4967cd1eeaa3bfac8d33bb5e16eb5502, built on frozen PR #47 SHA bb770d4e8c0bb1ebfcc630b8dfefc23c9eb790cb. It does not change any predecessor file or frozen branch. PR #48 root/provenance remains separate and unintegrated.

## What Agent 06 proved in the original same-UID prototype

- **P1-F47-01:** QA #25/#33: attacker-owned unsigned release + forged user-owned journal/pointer can be accepted by old recover(). Root cause: user-owned authoritative state, no independent authentication.
- **P1-F47-02:** QA #26: an attacker inserts foreign journal bytes after equality check, before os.replace; a cooperative lock and dirfd do not prevent user-owned namespace overwrite.
- **P1-F47-03:** QA #29: inherited AF_UNIX socket SO_PEERCRED can represent socket creation-time parent, not actual per-message sender or authorized human request.
- Existing 33 independent QA tests, all 28 original Agent08 tests and 18 earlier Agent06 tests remain UNCHANGED and execute in the new CI. Their intentionally positive old-model vulnerabilities remain reproducible; they are not rewritten to fake a pass.

## Proposed Linux privilege boundary — actual disposable root vs UID 65534 tests

GitHub-hosted Ubuntu 24.04 runs one ephemeral ROOT subprocess as the broker and separate independently exec'd UID 65534 hostile clients. The root subprocess uses a random root-owned temporary /tmp/flight-agent08-* directory; /tmp's root-owned sticky semantics prevent an ordinary UID from swapping that root-owned entry. The root-owned public socket parent is non-writable by others; all protected trust, release, journal, lock, active and ledger subdirectories are root:root 0700. Test-ephemeral HMAC secret and pinned signer public keys are root-only 0600 files. This is **actual kernel discretionary-access-control evidence**, not a Python chmod simulation. It does not install a service or write systemd/sudoers/polkit, and does not validate a production binary. Production requires an audited, separate system-controlled identity and immutable executable/dependencies under root-owned, unwritable ancestors, NOT a temporary /tmp store.

**Threat model:** attacker controls ordinary interactive user processes and files, including same-UID Python, GUI, paths and downloads, but cannot gain root, tamper with kernel, alter root-owned trust pins, or write/rename any protected ancestor. Root/admin, kernel compromise, signing authority compromise, other namespaces and ptrace bypasses are separate reviews.

### Per-operation authorization

Broker accepts AF_UNIX SOCK_SEQPACKET requests with exactly one SCM_RIGHTS artifact FD and canonical signed metadata. Linux SO_PEERCRED is recorded as telemetry, **never** treated as proof of per-operation consent. Instead, broker validates independently pinned Ed25519 signed operation tickets with a domain separator and exact operation activate, application/channel, artifact sequence and digest, expected protected previous sequence/digest, 128-bit nonce and bounded validity. Ticket signing private key is created in the privileged test harness RAM; the separate UID 65534 client executes after dropping inherited groups, UID, GID and exec, so it has no signer private key. Broker independently verifies the release against a distinct root-owned test pin and validates seals, size, digest and identity on the exact FD after transfer.

**Limit:** the test ticket is a transferable bearer capability. Malware stealing a previously issued valid unused ticket and its matching signed bytes could race activation. This test is proof of independently verifiable cryptographic operation authorization, not proof of a secure user consent UI, enrollment, session binding or production ticket custody. Real production requires reviewed polkit/OS authorization or independently signed rollout authority plus anti-token-theft controls and explicit owner approval.

### Broker-owned journal and active pointer

One root-only app lock serializes trusted startup recovery and signed activation. New inert release blobs are written via O_EXCL | O_NOFOLLOW relative to trusted directory FDs, fsynced before they are referenced. Transaction journal is **append-only immutable per sequence** in the CI model: a new O_EXCL txn sequence file is created, fsynced and authenticated with a root-secret HMAC. There is no compare-then-os.replace journal update. Each journal entry records sequence, expected predecessor sequence/digest, release content digest, manifest hash, ticket hash and consumed nonce. Recovery traverses complete monotonic chain, rejects malformed/missing entries, duplicate nonces and changed release content. Replays and downgrades are rejected under the lock.

Active pointer updates use a root-owned temporary and atomic replacement inside a trusted root-owned directory; the original old-model race is blocked because ordinary UID processes cannot modify this destination or any ancestor. Unexpected pointers and unauthenticated or foreign records are NOT silently overwritten. After crash before journal commit, release remains inert orphan; after authenticated journal commit, a fresh root broker process verifies journal/bytes and may roll forward from the exact previous activation. Unprivileged IPC does not expose recover/rollback/shell/start/stop services or SDR APIs. Background OFF. The prior v0.3.1 archive, installed 0.3.2.dev4, pipx, QSettings/XDG, SDR data, settings, recordings and borrowed readsb/tar1090 must remain untouched and are not opened by this CI harness.

**Limit:** root-owned HMAC and increasing sequence represent protected CI-local anti-replay, NOT an external trusted monotonic/TPM counter, anti-root snapshot restoration, actual power-loss durability, signed rollback policy or real application installation. The harness uses a fixed synthetic clock for deterministic tests; trustworthy expiry/revocation freshness and actual user consent remain HOLD. All filesystem data are inert bytes; no real package extraction, launch, uninstall or cleanup.

## Root/provenance PR #48 future trust interface — DO NOT INTEGRATE YET

A future reviewed broker should accept an independently bootstrapped root anchor, authenticated role-specific release/build/source signing policy, signer fingerprint revocation inherited across root epochs, signed build attestation and artifact digest/size/sequence. The protected broker must obtain pinned trust independently from the ordinary user and must never allow client-supplied key dictionaries. Broker authorization ticket and signed release verification must be independent cryptographic authorities with narrow distinct roles. Freeze PR #48 and its independent QA history; do not claim root/provenance integration or that its prior transition gaps are closed. Any future adapter needs separate Agent 06/07 QA and owner approval.

## Cross-platform and test boundaries

Windows would require a protected service identity, NTFS ACL/ancestor enforcement, named-pipe token checks, audited DuplicateHandle and reparse-aware handle-relative file access, UAC/operation authorization and durable recovery. macOS requires a signed root-controlled launchd/SMAppService privileged helper, XPC audit identity/designated requirements, Authorization Services, hardened file descriptor transfer and APFS durability review. These are **NOT IMPLEMENTED, TESTED, OR CLAIMED PARITY**.

The 20 new tests cover REAL kernel root vs ordinary UID inability to write protected files, rename root-owned public ancestry, replace immutable transactions or redirect activation; separate-exec unprivileged SCM_RIGHTS requests, invalid ticket and signature rejection, replay/sequence/nonce, valid version updates, simulated crash cuts with fresh root process, malformed-frame descriptor cleanup and orphan temp preservation, inherited peer UID insufficient without ticket, and foreign-file preservation. Existing 79 original tests continue to reproduce old simulator gaps. All proof uses GitHub-hosted disposable Linux only, no real production keys or hardware.

### Risk / acceptance gates

| Gate | Decision |
|---|---|
| P0 | No new production finding asserted; no production broker exists |
| P1-F47-01/02 | Targeted scoped real Linux DAC negative acceptance only if exact-head CI confirms; old same-UID prototype remains insecure; production installer HOLD |
| P1-F47-03 | Cryptographically independent, exact per-operation authorization ticket scoped acceptance only; bearer theft and genuine OS consent still HOLD |
| P1 trust root / build provenance | HOLD pending independent PR #48 integration and review |
| P1 protected monotonic rollback/freshness / real authorization | HOLD — synthetic clock, no signed rollback, no trust-resistant root snapshot state |
| P2 native crash/power-loss, cleanup and foreign ledger | HOLD — only logical crash cuts, no SIGKILL/power loss, no native installer |
| P2 macOS/Windows separate-principal broker | HOLD — design only |
| Owner machine, real services, SDR, merge, release | NOT TOUCHED / HOLD |

**PUBLIC RELEASE HOLD.** Explicit owner approval and independent Agent 06 exact-head QA required before any real privileged helper or integration.
