# Agent08 — PR #52 independent QA remediation: explicit authority, manifest identity and retry

**PUBLIC RELEASE HOLD.** CI-only architecture and proof; NOT a production broker, user-consent UI, system package or release.

Exact frozen ancestry:
- Agent08 development PR #51: 97aea7ebe3975e1976dd6e0eb71b0a30533138c0.
- Independent Agent06 QA PR #52: f13d8e00afdcad276611cba31d1bef57986ba877.
- This new Draft is based DIRECTLY on PR #52 exact SHA. PR #52's original 15 tests and its deliberate positive vulnerability witnesses remain unmodified. PR #50/#47/#42 positive and negative controls remain unmodified; PR #48 root/provenance remains FROZEN and UNINTEGRATED.

## Why an isolated v2 instead of rewriting v1

The old root-vs-UID65534 broker uses a signed transferable bearer ticket. It does not prove that a user approved the current process. Original independent QA #06 proves a stolen valid unused ticket can authorize. Original QA #12 shows the same signed ticket authorizing two genuinely release-signed manifests of identical bytes/sequence but DIFFERENT source_commit. Original QA #13 shows release fsync before journal leaves an orphan that blocks an otherwise legitimate retry. All are meaningful evidence and must remain green as *positive demonstrations of the frozen old vulnerability*. Altering or disabling those tests would be a false remediation.

The isolated new code and tests live in:
- tools/flight_p1_broker_pr52_remediation_ci.py — BrokerV2 reference, root-owned approvals and prepared receipts, actual per-message SCM_CREDENTIALS.
- tools/flight_p1_broker_pr52_remediation_tests.py — new real UID/DAC negative acceptance and valid-operation controls.
- .github/workflows/flight-pr52-broker-remediation-agent08.yml — disposable Ubuntu 24.04 root-vs-UID65534 acceptance and all frozen QA suites.

No owner desktop, production code, sudoers/systemd/polkit configuration, installed helper, external services, archives, SDR, readsb, tar1090, secrets or releases are modified.

## P1 stolen-ticket and independent per-operation boundary

**CI model, not production human consent.** A privileged ROOT-only test authority explicitly approves an operation for a *pre-existing, independently exec'd UID65534 process*, by writing a root:root 0600 HMAC-authenticated approval into a 0700 private directory. Public broker IPC has NO approval or signing endpoint; UID65534 cannot create or edit the approval. The approval is bound to the exact operation ticket SHA-256, signed-release manifest SHA-256, detached signature hash, nonce/sequence and Linux sender PID, UID and /proc start ticks. This distinguishes a root-approved process from a different, same-UID attacker that merely steals a valid unused bearer ticket.

The broker receives **SCM_CREDENTIALS per received message with SO_PASSCRED**, not only stale SO_PEERCRED from socket creation; an inherited connected socket child does not inherit the parent's separate root approval. All checks occur in root broker while holding its root-owned transaction lock. One valid operation consumes the journal sequence/nonce, so a second use is rejected. Missing, forged, unknown, stale, mismatched or tampered approval is fail-closed.

**Remaining P1 / limits:** A real independently trusted human authorization or enterprise rollout policy is NOT present; the trusted CI root-side approval is issued explicitly by a test harness, not by an OS prompt. The approval is bound to process identity, NOT guaranteed resistant to a malicious same-UID debugger/ptrace/injection of an already approved process, process inherited non-socket capabilities, compromised root, token capture inside the approved process, kernel attacks or reboot identity reuse. Production must use a reviewed polkit/OS-mediated consent boundary, protected client process/session and request identity, or independently signed rollout channel. No user-consent parity or deployment approval is claimed. Refuse all ordinary requests without a root-side approval.

## P2 exact canonical signed release identity

V2 uses a new signed operation-ticket schema and Ed25519 domain (schema=2, TIHULU_FLIGHT_BROKER_OPERATION_CI_V2). It binds original app/channel/action, exact release artifact size/digest/sequence and expected prior activation/nonce/time PLUS:
- SHA-256 of the **complete canonical signed release manifest bytes**;
- SHA-256 of detached Ed25519 **release signature**;
- exact signed source_commit field.

The complete canonical raw manifest hash therefore commits to all presently signed fields, including source_commit, key identity, channel/platform/arch, artifact SHA256 and size, and timestamps. A second correctly release-signed manifest with the SAME artifact bytes and sequence but a DIFFERENT source_commit is rejected under the original operation ticket (not mistakenly approved by content-only equality). The signed release and operation keys are separately root-pinned ephemeral CI keys. The existing legacy schema lacks real signed build/workflow attestation; this model can bind to signed **source_commit** claims but cannot authenticate external provenance or a real build pipeline. Future PR #48 trust adapter needs independently reviewed canonical build/source attestation and genuine protected enrollment; none is imported here.

## P2 authenticated orphan staging and retry

V2 writes a root-owned, HMAC-authenticated immutable preparation receipt under the same root-only lock BEFORE creating inert blob bytes. Receipt is strictly bound to full manifest and release signature hashes, exact ticket hash, 128-bit nonce, expected previous activation, sequence and derived release filename/digest. After receipt fsync, release is created with O_EXCL and fsynced. Only then is the old format append-only HMAC journal commit written with O_EXCL and fsynced. Finally the activation pointer is published via existing protected root-only rename/fsync.

When an approved request fails after receipt or after release fsync but BEFORE journal commit, a retry of **the exact still-valid authorization from the same approved process** checks:
1. HMAC-protected receipt matches all expected signed transaction identity fields.
2. Existing release (if any) is root-owned, no-follow, one link, non-writable to others, exact signed length/content/SHA256. If absent, a new blob is staged.
3. Current trusted journal and previous activation are unchanged and monotonic; approval is valid for that process and no nonce has been committed.
4. Only after these checks does the broker commit journal and activate. Old versions, unrelated foreign bytes, recordings, and unknown files are preserved; no unlink, cleanup or mutation of an unrelated name is performed.

A foreign pre-existing blob **without a signed prepared receipt**, tampered receipt HMAC, wrong previous state or modified orphan bytes causes HOLD without deleting it. A crash after authenticated journal commit is handled by trusted root startup reconciliation; repeating a consumed transaction fails as replay. Tests inject logical after_prepare and after_release cuts and restart a fresh root subprocess, then retry using actual UID65534 clients; these are NOT real power-loss, random SIGKILL, fsync fault or storage-controller guarantees.

## Threat and acceptance mapping

| Independent finding | New v2 scoped CI plan | Remaining |
|---|---|---|
| **P1 stolen unused ticket** | Real UID65534 stolen request denied without root grant, and denied from a different same-UID PID even while an independently root-approved process has an unused grant; inherited socket child bound to its per-message kernel identity | TRUE human consent / same-UID process injection / protected non-transferable session still P1 HOLD |
| **P2 exact manifest identity** | Correctly release-signed alternate source_commit rejected with same valid operation ticket; exact v2 manifest and detached signature hashes required; approved original works | Genuine builder attestation/source provenance and PR #48 integration HOLD |
| **P2 crash orphan retry** | MAC receipt + protected root-owned blob + exact identical approved ticket permits after_release/after_prepare retry; corrupt/foreign receipt and bytes retained and denied | Actual SIGKILL, disk full, fsync failures and power loss, owner production acceptance HOLD |

### Distinguish actual kernel behavior from simulation

Real: hosted Ubuntu ROOT broker subprocess and independently exec'd UID65534 client, chmod and kernel DAC enforcement over actual root-owned directories, SCM_RIGHTS sealed memfds, SCM_CREDENTIALS per message, Linux process identity and fsync/rename of disposable test files. Synthetic/test authority: ROOT CI-side approval instead of human intent, ephemeral RAM signer keys, synthetic fixed CI_NOW, in-memory issuance, HMAC-only CI local journal and logical crash hooks. Previous PR #52 and PR #50 positive tests remain green **on the old insecure broker**; a green old exploit is not production security clearance.

**P0:** no production broker exists, no production P0 clearance. **P1:** root custody, independently reviewed genuine OS user approval and process injection resistance, production installed separate-UID service, authentic PR #48 trust/root, trusted anti-rollback/freshness and online revocation remain HOLD. **P2:** genuine source/build provenance, full crash durability, ordinary-client rate limiting, safe cleanup, foreign ownership ledger, Windows/macOS native helper parity remain HOLD until independent review. No merging or public release.

**Review:** Agent 06 must independently examine exact new head SHA, reproduce negative attacks and explicit positive original witnesses, and classify P0/P1/P2. Source/model **SCOPED PASS only after exact-head CI logs prove nonzero test execution**; user machine, real installs/SDR/production release remain HOLD. **PUBLIC RELEASE HOLD.**
