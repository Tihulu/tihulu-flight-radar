# Flight PR #40 — P2-F39-01/02 CI trust API and FD ownership hardening

**Status: disposable CI-only, PUBLIC RELEASE HOLD.** This file documents
scoped API improvements on a NEW isolated Draft stacked on Agent 06 frozen
independent QA PR #40 `19b078a653b7c32d74b68c2a61e2424276d0f953`.
Nothing in this branch signs a real artifact, opens the owner's machine,
installs/uninstalls software, or changes previous PR branches.

## Scoped change 1: no fabricated trusted objects through public constructors

The previous CI-only `VerifiedMetadata(**fields)` public dataclass accepted
invented unsigned fields; `SealedFixture(fd, metadata, size)` accepted an
ordinary *unsealed* FD with a fabricated policy. This conflated an object
type with cryptographic source authorization.

Both **public constructors now fail closed**, even with correct-looking
fields or an FD with correct length. The only supported path is
`verify_and_seal(...)`: it validates canonical Ed25519-signed policy using a
separately caller-pinned test public key, reads the candidate from the
previously opened source FD, validates SHA256 over copied bytes, seals memfd
with all four required Linux seals, then internally mints the resulting
fixture after a final seal/digest/identity/length check.

`VerifiedMetadata` remains a frozen 13-field, flat typed mapping and
`SealedFixture` remains frozen/slotted. There is no public constructor
asserting trusted provenance. **Private helper functions, Python reflection,
`object.__new__` and compromised interpreter code are NOT secure
authorization boundaries.** A malicious same-process caller capable of
executing arbitrary code can bypass Python API checks or alter trusted
policy/key inputs; this remains explicit production P1 HOLD.

## Scoped change 2: private FD owner, no public raw integer capability

Prior `artifact.fd` returned the **owner's actual** kernel FD number. Any
consumer could `os.close(fd)` and reopen an unrelated same-length file
reusing the number. The old `read()` read foreign bytes, while `close()`
would close a foreign FD.

The public `fd` property is **removed**. Public consumers can only call
`read()`, `close()`, `verified_length` or inspect frozen metadata. The
verifier owns the FD from successful sealed construction until explicit
close. It stores the validated `st_dev/st_ino`, verified length, four
required seal flags and digest as a separate immutable snapshot. Each
`read()` checks FD identity/seals/length, positional-reads only the verified
size, checks its SHA256 and rechecks identity/seals before returning.
`close()` clears the owner's pointer first; if deterministic white-box
same-process code closed/reused the *private* integer, close reports HOLD
and deliberately **does not close the foreign descriptor**. Normal
`close()` is idempotent and use-after-close fails.

The private `_fd` slot exists so the Python module can operate; the audit
regressions deliberately access it in WHITE-BOX tests to demonstrate the
hostile-interpreter limit. That is **not a supported public FD access
method**, and `_fd`, `object.__setattr__`, monkeypatches, raw `os.close`
and Python process memory are still accessible to malicious code in the
same interpreter. `fstat` -> `close` itself is not atomic against a
concurrent malicious interpreter or hostile same-UID process able to
manipulate this process's FD table. Such a threat remains **P1 HOLD**; no
cryptographic or file-seal guarantee is claimed for an arbitrary attacker
that can control the verifier process.

No real installer/consumer FD handoff is implemented. Before a future
cross-process transfer, design a narrowly authorized trusted broker,
explicit `SCM_RIGHTS`/platform-specific handle-transfer ownership,
authenticated sender/receiver identities, and verification of seals,
size/digest and FD identity in the broker *after transfer*. The broker
must be the actual OS-enforced owner of its destination and activation
paths; accepting a verified FD does not protect a same-UID-writable target.

## Acceptance and frozen independent evidence

Frozen Agent 06 PR #40 remains unchanged, including its POSITIVE threat
reproductions #15/#16/#17. Only in this separate remediation branch,
the old tests #15/#16 become **negative acceptance** for direct
construction and recycled private FD; #17 deliberately remains POSITIVE
evidence that Python frozen fields are not same-process isolation.

- Author's 29 earlier tests retained plus scoped constructor/FD reuse,
  identity, digest and foreign-close tests.
- Independent Agent 06 PR #38 derived 22 tests retained; their white-box
  seal and spoof-read controls now reference private `_fd` in CI only.
- Agent 06 PR #40 derived 17 tests retained with #15/#16 inverted, #17
  explicitly positive; no release approval inferred from green tests.
- Every test runs exclusively on GitHub-hosted disposable Linux CI,
  signing keys are ephemeral test-only RAM keys.

## P0/P1/P2 and next production trust gates

| Area | Decision |
|---|---|
| P2-F39-01 public unsigned metadata + unsealed FD wrapping | Scoped CI PASS only when exact-head negative tests succeed |
| P2-F39-02 public raw FD ownership/recycled FD foreign-byte read and close | Scoped CI PASS only when exact-head negative tests succeed |
| Existing signed schema, Ed25519, one-open copy, memfd seals, frozen metadata and fixed read length | Retain prior CI acceptance; re-run at exact SHA |
| Python reflection / unsafe private access, malicious same-process FD substitution between stat and close | **P1 HOLD**; API is not an OS trust boundary |
| **P1-ROOT:** authentic signer/key custody, trusted offline keyring bootstrap, revocation, source/build attestation | **P1 HOLD** — not implemented |
| **P1-INSTALL:** independently protected broker executable/keys/journal and destination/activation vs hostile same-UID | **P1 HOLD** — not implemented |
| **P1-ROLLBACK:** durable monotonic replay/rollback state and trusted freshness/clock, offline recovery | **P1 HOLD** — not implemented |
| Cross-platform native handle ownership, crash/power loss, sandboxed extraction, real rollback/uninstall | HOLD / not tested |
| Installed v0.3.2.dev4, legacy v0.3.1, pipx, QSettings/XDG, sudoers, readsb/tar1090 and RTL-SDR | NOT TOUCHED / NOT TESTED |
| Independent Agent 06 exact-head PR re-review; merge/install/public release | HOLD |

**Next architectural phase** is a separately reviewed CI-only broker model
with genuine authenticated policy bootstrap, a persistent trusted
anti-rollback journal, and OS-protected storage independent of the hostile
same-UID principal. No global `flock("/")` from a synthetic lab is
suitable for real installer locking. Do not merge, install, uninstall,
release or operate the owner's hardware.
