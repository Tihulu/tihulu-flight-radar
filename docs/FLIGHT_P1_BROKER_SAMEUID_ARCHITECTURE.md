# Flight Radar — Agent 08 P1-BROKER / SAME-UID security foundation

**STATUS: CI-ONLY CONTRACT MODEL / PUBLIC RELEASE HOLD.** This document specifies an OS-enforced privileged broker architecture; it is **not** a deployed service, secure production installer, production signing root, user-host proof, or native cross-platform parity.

**Frozen independent starting baseline:** Agent 06 PR #42 exact commit 324c267ca38ad15c176be243e21dd4477a5781cb (original 18/18 CI security tests). PR #43/#44/#45 and their branches remain untouched and unmerged. This new Draft stacks on the exact PR #42 commit and does not borrow or claim to integrate the Agent 06/07 root/provenance work.

## Threat model: same ordinary UID is hostile

Attacker: arbitrary unprivileged code executing under the same ordinary interactive account as Flight GUI/launcher; can change user-owned modes, files, processes, Python state, environment, socket request contents, downloads, paths, directories, and symlinks. The attacker may request installation of a signed release. The attacker is not assumed able to gain admin/root rights or rewrite genuinely OS-protected signing roots, kernel controls, or broker storage. Production signer compromise, hostile administrators and fully compromised runtimes are separate security gates.

**A Python private field, process-owned memory, chmod 0700, SO_PEERCRED.uid, a cooperating flock, pathname rechecks, or a sealed user-owned memfd cannot separate two processes of the SAME UID.** A secure broker MUST be a separate OS-protected principal. Its executable, installed code dependencies, trust pin/role policy, protected rollback state, release namespace, ownership ledger, journal, transaction lock, activation pointer and **all mutable ancestors** must be unwritable and unrenameable by the ordinary user. The ordinary account may read/execute approved application bytes but may not write, replace, redirect or activate protected releases.

Authenticated peer identification is necessary but not sufficient to authorize privileged changes. A same-UID attacker can impersonate GUI intent. Require a narrowly scoped, broker-reviewed **independent user-approval mechanism** for interactive activation or a separately signed authorization for unattended rollout, including operation, app ID, channel, version/sequence, expiration, nonce, target and expected previous activation. Do not use TOFU from client-supplied keys. Rollback needs a separate signed safety ticket, minimum-safe-version policy, trusted freshness and human/enterprise approval. **This Draft implements none of the real protected authorization/prompt infrastructure.** Its CI fake broker processes run under the ordinary test UID, and therefore remain mutable.

## Proposed Linux / Pop!_OS 24.04 architecture (NOT deployed)

| Protected object | Proposed owner and controls |
|---|---|
| broker binary and local policy | system-owned executable, audited dependencies, no ordinary-user write/rename rights at every ancestor |
| trusted signing root, signer roles and revocation policy | independently provisioned protected root pin; no caller-substituted public key, verified expiration, revocation lineage and root rotation |
| IPC endpoint | protected local Unix socket under /run; kernel SO_PEERCRED plus separate operation authorization/consent |
| release blobs and stage | root/system-controlled namespace such as /opt/tihulu/flight-radar/releases; ordinary-user read-only access where required, no untrusted writable ancestors |
| lock, journal and ownership ledger | broker-only persistent directory such as /var/lib/tihulu/flight-radar; fsync, trusted previous state, exact file ownership |
| activation pointer | dedicated system-owned atomic pointer with expected previous ID; fail closed on foreign/symlink data |
| anti-rollback/freshness | protected monotonic record and signed rollout / recovery policy, independently checked during each transaction |

**Paths are only examples, not created in this PR.** The broker must be least-privileged and strictly operation-allowlisted (no arbitrary shell, user paths, service manager or subprocess control). On-demand only; default Background OFF. It must never start, stop, take ownership of, or reset borrowed readsb/tar1090, Jan, another app's SDR/tuner, or other shared processes. Original Flight 0.3.1 and 0.3.2.dev4, pipx install, legacy launchers, QSettings/XDG files, recordings, user settings and SDR archives must remain preserved. New releases use separate IDs and directories. Protecting release bytes does not itself isolate an ordinary runtime from hostile same-UID process injection; the runtime trust model is a separate review.

### Broker IPC + independently checked artifact FD

1. Client connects to a system-owned endpoint. Broker obtains kernel peer credentials and an independent scoped activation authorization. A claimed UID, a GUI token or signed manifest sent by the same user is NOT by itself an authorization to change state. Each operation is bound to nonce, transaction ID, expected activation, channel and version.
2. On Linux, client sends exactly one read-only candidate FD with SCM_RIGHTS. Broker receives with close-on-exec, rejects missing/multiple/truncated ancillary payload, wrong file type and closed descriptors. The broker never reopens an attacker-owned download pathname or accepts client-provided FD identity/verified Python object as authority.
3. **Within the protected broker and lock**, verify a separately pinned Ed25519 root/role policy, strict canonical signed metadata, app ID, platform, architecture, release channel, signer role/revocation/expiry, exact build/source provenance, allowed sequence/freshness, digest and size. Revalidate FD fstat identity, exact pread length, SHA-256, required Linux seals (WRITE, GROW, SHRINK, SEAL), postread identity/seals. A different sealed FD containing identical independently authorized bytes is semantically equivalent; integer FD numbers are not signed identities. The current CI contract reuses frozen PR #42 canonical signature checks, **not** full production builder/root provenance.
4. Stage only verified bytes into OS-owned, descriptor-pinned destination. For a full installer, require reviewed archive expansion limits, no traversal/symlinks/hardlinks/devices, quotas, explicit ownership ledger, and signed installed-tree verification. THIS CI MODEL STORES ONLY INERT BLOBS. It does not extract, launch, install, uninstall, or create a privileged service.
5. For every directory ancestor use a broker-owned pinned directory descriptor and audited openat2 (RESOLVE_BENEATH, RESOLVE_NO_SYMLINKS) or openat (O_DIRECTORY | O_NOFOLLOW) component walk. Create fresh files with O_EXCL | O_NOFOLLOW; directory-relative renameat2 RENAME_NOREPLACE for new release insertion, atomic replacement only for broker-owned expected pointers, followed by fsync. **A pinned FD can survive an attacker rename of the public parent**: no amount of fd pinning solves this without true OS protection of every public ancestor.
6. One app-scoped OS-owned transaction lock serializes install/rollback/recover through journal and pointer changes. Re-read and compare current committed epoch/previous activation under lock. Other applications' namespaces and resources remain outside the broker's capability and ownership ledger.

### Durable stages and recovery

Proposed commit stages: (A) verify/stage new release, fsync file and release directory; (B) write a protected journal PREPARE/COMMIT with signed digest, transaction nonce, previous and next release, monotonic counter and hash chain, fsync; (C) publish one protected activation pointer atomically, fsync directory; (D) finalize acknowledgement. Crash before B: leave old pointer and ambiguous staging for inspection, no silent cleanup. Crash after B before C: trusted broker validates journal lineage and verified bytes, replays under same lock, only against expected previous pointer. Repeated recovery must be idempotent and fail closed if state missing, foreign, corrupt, out of order or unexpectedly modified. No rollback may revive an unsafe/revoked release without separately authenticated safety policy.

**Model limitations:** a single CI current.json record, not a hash-chained append-only production journal, not a TPM monotonic rollback counter. Its fake parent is owned by the *same* test UID, not system-owned. Advisory flock and pre-rename equality checks provide no adversarial same-UID guarantee in that sandbox. It tests two logical crash hooks, not SIGKILL, real fsync power-loss behavior, or native package rollback. On interruption it intentionally leaves safe orphans or temp files rather than deleting any foreign data. That is a CI recovery/preservation tradeoff, not production acceptance.

## Other operating systems — boundaries specified only

**Windows: NOT IMPLEMENTED.** Propose dedicated least-privileged Windows service with system-controlled executable/configuration, protective NTFS ACLs including ancestors, broker-only release/activation/journal, independent per-operation UAC/authorization (user SID alone is not intent). Authenticated named pipe with token checks, narrow DuplicateHandle transfer and broker-side handle identity/digest/signature checks; reject junction/reparse-point races using native handle-relative/reparse aware APIs and reviewed ReplaceFile/NTFS durable transaction recovery. No service, signing certificate custody, handle QA or Windows parity in this PR.

**macOS: NOT IMPLEMENTED.** Propose root-controlled, code-signed privileged helper registered through the reviewed launchd/SMAppService mechanism; designated requirement, XPC audit identity and independent Authorization Services approval. Root-owned immutable helper and trust roots; handle transfer and signature/digest recheck in helper, nofollow descriptor-relative paths, APFS atomicity/fsync and durable recovery review. No privileged helper, entitlements, notarization, native testing or parity is provided.

## Disposable evidence, adversarial tests, safety

Files in this Draft:
- tools/flight_p1_broker_ci_contract.py: CI-guarded Python **contract simulator** with Linux SCM_RIGHTS receive, SO_PEERCRED, strict broker-side re-verification, pinned dirfd, exclusive release creation, logical lock and state recovery. Not a privileged service.
- tools/flight_p1_broker_ci_tests.py: 28 targeted hostile tests, real Linux FD transfer/seals, independent ephemeral RAM keys; missing/multiple/forged/replaced FD, symlinks, ancestor rename, wrong signature, lock contention, replay/downgrade, foreign data preservation, two crash cuts, recovery and version coexistence.
- .github/workflows/flight-p1-broker-sameuid-agent08.yml: disposable ubuntu-24.04, least contents:read, no real keys, compile + 28 new tests + original frozen PR #42 18 independent tests.

**Deliberately positive P1 witnesses:** test 17 swaps the user-owned public parent and shows the descriptor stays pinned while the public alias changes. Test 24 proves the same UID can overwrite the model's broker journal despite passing all in-process checks. Test 28 proves chmod 0700 does not isolate the UID from its own data. Green on these tests is evidence of *remaining vulnerability in the fake boundary*, not approval of production security. The model cannot test isolation between two distinct OS principals without actually provisioning a protected broker, which is prohibited.

### Severity and acceptance

| Priority / gate | Decision |
|---|---|
| New production P0 | Not assessable: no protected production broker exists |
| P1-BROKER / SAME-UID | **HOLD** — trusted code and all OS-owned protected ancestors/storage not implemented |
| P1-AUTH / provenance | **HOLD** — real client independent approval, actual root custody, genuine signed build attestation not implemented |
| P1-ROLLBACK / freshness | **HOLD** — independently protected durable monotonic floor, rollback ticket, reliable crash/power-loss semantics not implemented |
| P1 public pathname integrity | **HOLD** — dirfd model alone cannot stop same-UID public parent rename |
| P2 CI evidence cleanup | Intentional orphan/temp collision fail closed; ownership-safe reviewed cleanup and recovery policy not built |
| P2 Windows/macOS parity | **HOLD** — security boundary described but never implemented/tested |
| CI-only signed FD / contract | Scoped PASS only after verifying exact-head CI and test counts |
| Owner machine, install/rollback, device, UI, live services, merge, public release | **HOLD / NOT TESTED** |

Agent 06/07 must independently review the exact new SHA before any integration. Their PR #43/#44/#45 root/provenance work includes its own reported transition-policy gaps and is neither replaced nor certified here. Integration needs separate scoped design review and owner approval. No sudoers, systemd, privileged helper installation, real signing key, user workstation, live SDR, merge, release or deployment actions are authorized. **PUBLIC RELEASE HOLD.**
