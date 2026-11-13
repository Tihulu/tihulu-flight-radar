# Agent 08 — Flight PR #54 confirmed P2 security remediation

**PUBLIC RELEASE HOLD.** This is disposable GitHub-hosted CI-only Linux broker
security reference code. It does NOT install a real privileged service, issue
production keys, configure owner systemd/sudoers/polkit, merge or release.

## Immutable lineage and QA evidence policy

- Frozen development PR #53 exact HEAD:
  b68b248e6d9b22c00ea8695e975c7f40bd27866a
- Frozen Agent 06 QA-only PR #54 exact HEAD:
  ce13e5d6ce3c33ead3e665c2143cfff4dcb821a9
- New remediation branch is rooted **DIRECTLY** in PR #53 frozen HEAD, never
  PR #54, and edits only its copy of the CI-only V2 reference broker.
- Frozen PR #54 positive DoS (#26) and dead-original P2 (#23/#24) test witnesses
  remain UNCHANGED. CI explicitly checks out the frozen PR #54 exact SHA
  independently and re-runs its 28 cases against ORIGINAL frozen v2 code.
  These passing POSITIVE tests are proof of OLD deficiencies, never proof that
  this new broker is still vulnerable or secure.
- All earlier frozen QA/positive suites remain unchanged and execute on the new
  remediation branch (16 + 15 + 20 + 33 + 28 + 18 old tests).

## P2-F53-01 — unauthenticated local disconnect killed privileged broker

Original: a separately exec'd ordinary UID65534 untrusted client connects to
the root test broker AF_UNIX SOCK_SEQPACKET endpoint, shuts down and closes.
receive_v2() rejects the empty/malformed frame, but the unhandled
conn.sendall() of an error reply throws BrokenPipeError **outside** the
exception handling. Actual old broker process exits. This is a local
availability defect in the *disposable* privileged harness.

New server: request parsing, independent approval and FD close remain
fail-closed. Sending a reply is now wrapped in its **own exception boundary**;
BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError and
other socket OSError are contained *per connection*, never propagated to the
root accept loop. The privileged broker owns its listening socket until the
test ends. No authentication, manifest validation or approval check is relaxed.
Root owns its protected state and closes received SCM_RIGHTS descriptors even
if request processing fails. Peer-request recv timeout stays bounded at 3 sec.

**New real kernel UID acceptance:** repeated separate UID65534 immediate close,
shutdown, malformed frames and multiple SCM_RIGHTS FDs cause NO crash and NO
journal/activation. A subsequent independently root-authorized, per-message
SCM_CREDENTIALS validated signed transaction must succeed in that SAME
still-running root broker process; the tests assert its process has not died.
This verifies continuity on ephemeral Ubuntu runner, not complete
production DoS resistance: bounded worker pool, flood/rate limiting, socket
permissions, fd exhaustion, signal and syscall fault hardening remain open.

## P2-F53-02 — dead original approved PID stranded a protected preparation

The original V2 immutable HMAC PREPARED receipt was bound to the old operation
ticket SHA256 and nonce. A SIGKILL of the original approved PID after receipt
or inert release fsync made another independently approved process unable to
resume. The old broker properly refused foreign bytes, but lacked a narrowly
reviewed owner-authorized handoff protocol.

**Chosen security protocol: explicit root-only transfer, NOT deletion or
automatic new-process adoption.** Public broker IPC still exposes only the
signed activate request. A separate ROOT-only test-authority API,
authorize_takeover_from_root_test_authority(), performs this under the original
root-owned transaction lock:

1. Verify entire authenticated monotonic journal and expected old activation.
   Independently check newly signed Ed25519 V2 operation ticket, exact canonical
   release manifest SHA256, detached signature SHA256, signed source_commit,
   artifact digest/size, expected previous activation and nonce/time.
2. Verify the new *live* replacement UID65534 client's fresh root-issued
   per-process HMAC authorization, its PID and /proc start ticks. The new process
   MUST have a separate signed ticket and nonce, not the dead process's
   transferable token. No ordinary socket call can issue the new approval or
   execute root takeover.
3. Require a pre-existing ROOT-owned, O_NOFOLLOW, single-link HMAC-authenticated
   immutable original PREPARED record bound to manifest/signature/digest,
   expected prior activation, seq, original nonce and ticket SHA256. Fetch and
   verify the original root-owned independent approval receipt tied to this
   first transaction.
4. Verify **actual original process identity is gone** by reading /proc/PID/stat
   start ticks. An existing process with the original ticks (including zombie)
   denies takeover; unverifiable /proc state fails closed; recycled PID with
   changed ticks proves *original process* is no longer the same kernel process
   for the modeled scope. This is NOT production pidfd or reboot-identity proof.
5. Compare the old and replacement proposed records on **every immutable
   release field**: sequence, root-owned release name, content digest, exact
   canonical manifest hash, exact release-signature hash, previous seq/digest.
   Any change rejects. New signed ticket hash and nonce MUST differ from old;
   new independently approved process identity must be distinct.
6. If a staged blob exists, read it through broker-owned directory fd with
   O_NOFOLLOW/ownership/nlink permissions checks; exact signed byte length and
   SHA256 must match. Foreign/altered bytes are left untouched, no adopt.
7. Write **one new immutable HMAC-authenticated** transfer receipt under a
   separate ROOT-owned 0700 handoff/ directory via O_EXCL, fsync file+parent.
   Receipt binds original PREPARED file SHA256, both approved client identities,
   original/new operation SHA256 and nonces, exact signed manifest/old state,
   seq/release/digest. An EXACT same root-side transfer reissue is idempotent;
   any competing different transfer fails closed and preserves original bytes.
8. Normal new client activation still re-verifies signed metadata/ticket,
   separate root approval, kernel **per-message SCM_CREDENTIALS**, signed FD
   seals/digest and all journal/freshness conditions under the same lock.
   On an otherwise mismatched original PREPARED record it accepts ONLY if the
   separately HMAC-verified transfer matches every original/new field, and the
   original session is still dead. It reuses only matching root-owned inert
   staged bytes (or writes the absent bytes) before committing the single
   O_EXCL journal and activating the protected pointer. Original PREPARED
   and foreign files remain unmodified.

There is NO automatic "release orphan belongs to us" inference based solely
on filename/contents; the prior independent signed PREPARED + both root grants
+ explicit immutable transfer receipt are required. Neither a new stolen ticket
nor normal independent approval alone permits adoption. A persistent
original receipt with a corrupt HMAC, manipulated blob, foreign transfer file,
different source_commit, old live process or changed prior activation results
in HOLD. No unrelated recording/settings/legacy app, readsb/tar1090 or SDR
file/service is accessed.

## Scope, risks and evidence boundaries

**Actual OS-enforced checks:** disposable GitHub-hosted Ubuntu UID0 separate
root broker process and exec'd UID65534 clients; Linux kernel DAC on root-owned
0700 storage and ownership; SOCK_SEQPACKET/SCM_RIGHTS/SCM_CREDENTIALS;
real SIGKILL and wait/reap of original client, fresh root broker subprocess,
real Unix socket connect/shutdown/reset; fsync and dirfd O_NOFOLLOW/O_EXCL
on ephemeral inert fixture bytes. These are REAL kernel interactions.

**Synthetic/test-only:** Ed25519 ephemeral private keys, explicit ROOT CI test
approval instead of human authorization, fixed synthetic trusted clock,
file-HMAC without protected hardware monotonic counter, *logical* broker
crash cuts (not true power loss or kill at arbitrary syscall point), /proc
start-ticks process-identity hint (not pinning a pidfd across reboot).
The root-owned temporary /tmp directory with sticky parent is *not* a genuine
installed immutable broker code/trust boundary. A same-UID attacker injecting
into a previously approved running client, another root actor or client death
while root handoff itself is interrupted require additional security review.
The one-replacement receipt is intentionally fail-closed rather than offering
arbitrary future transfers, so a second successor may require a separately
reviewed ROOT-authorized abort/transfer version 2; NEVER delete foreign bytes.

**P0:** no newly demonstrated production P0 or production clearance. **P1:
HOLD** genuine human/enterprise OS authorization, root signer custody,
root/provenance PR #48 integration, production helper/installer trust
bootstrap, process injection/pidfd lifetime/reboot correctness, durable
trusted freshness and rollback. **P2:** scoped CI remedy for local peer
disconnect and new-process takeover **only if exact-HEAD nonzero tests pass**;
Windows/macOS OS-level helper, arbitrary SIGKILL/fsync/power loss, crash safe
abort of an incomplete handoff, foreign owner ledger, cleanup and denial-of-
service/resource limits remain HOLD. **Public release/merge/install and
owner-machine access: HOLD.**

Independent Agent 06 QA must adversarially challenge exact SHA, especially
peer-close after signed commit, HMAC PREPARED/approval/handoff tampering,
competing root transfers, unprivileged takeover spoof, PID recycling,
original process survival/injection, foreign bytes, source_commit changes,
sequence/nonce replay and kill/reboot cuts. Preserve original frozen QA #54
positive proofs. Never call this a deployed protected service.
