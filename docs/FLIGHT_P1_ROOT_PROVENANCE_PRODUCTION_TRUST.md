# FLIGHT P1-ROOT / PROVENANCE — executable production trust design

**CI-ONLY PROTOTYPE. PUBLIC RELEASE HOLD.** This document describes a testable architecture, NOT an installed release verifier, production signer, or trusted key ceremony. Its synthetic test private keys are created in RAM only on disposable GitHub-hosted runners. No real or purported production public/private key is embedded, generated, distributed or authorized.

**Frozen ancestry:** Development PR #41 exact d558d0efd71999e644d4e4ab6762db5dc9fc42dd, independent Agent 06 QA PR #42 exact 324c267ca38ad15c176be243e21dd4477a5781cb. New code is on a separate Draft branch stacked precisely on QA #42. Do not mutate older PRs, their tests, running Flight Radar, or the owner's hardware.

## Implemented (bounded synthetic CI only)

The executable model in tools/flight_p1_root_provenance_ci.py provides:

1. Strict canonical signed JSON with duplicate/unknown member rejection, fixed field schemas, restricted key IDs, byte bounds and domain-separated Ed25519 verification for root, source, builder and release documents.
2. Caller-supplied public key roster and a separately authenticated SHA-256 fingerprint checked before initial ROOT policy acceptance. The first root must contain EXACTLY that roster and threshold. This models independent out-of-band pinning; calculating the fingerprint from the same download as the root policy is NOT authentication.
3. Initial 2-of-3 ephemeral root signatures. Root rotation requires BOTH old-root and proposed-new-root signature quorums. Versions advance exactly one, previously revoked IDs remain revoked, retiring an authority requires explicit revocation, and root/source/build/release roles cannot silently share key material or repurpose an existing key ID.
4. Explicit SOURCE reviewer role signs repository, ref, commit and source tree digest. The verifier requires separately provided expected commit/tree. Explicit BUILDER role signs the exact source claims, source-attestation digest, builder-workflow identity, recipe/materials digests and built artifact hash/length. Explicit RELEASE role signs authorized app, channel, platform, architecture, artifact name, release sequence, root version, source/build attestation digests and artifact details.
5. Verification compares ACTUAL supplied artifact bytes with the authorized SHA-256 and length. Wrong signer role, forged signature, wrong source commit/tree, unexpected repository/ref, builder identity mismatch, detached/forged attestation, wrong target/arch/channel, rotated/revoked key, root downgrade and corrupted artifact fail closed.
6. Untrusted callers cannot use public constructors to fabricate the returned frozen RootAuthority or VerifiedProvenance records through the ordinary API. Malicious same-interpreter Python code and reflection are explicitly outside this protection.
7. The dedicated tools/flight_p1_root_provenance_ci_tests.py suite exercises positive functional checks, adversarial controls and deliberately positive demonstrations of UNRESOLVED trust limitations.

This prototype does not install/unpack/activate anything and is not yet wired into the older sealed-FD verifier. A signed provenance *claim* is not independently verified evidence that GitHub or another builder actually ran the asserted workflow.

## How production trust would have to be bootstrapped

**P1-ROOT remains production HOLD pending actual enrollment.** A separate operator review must establish the trust authority, key custody, signing quorum and real-world independently authenticated root key distribution. Use a reviewed offline root key ceremony with independently controlled hardware or air-gapped private key holders, documented recovery and compromise procedures, tamper-evident authenticated public key roster and SHA-256 pin delivered outside the update/artifact channel, and audited dual-endorsement rotation. This test suite invents no actual production signing key and cannot attest physical key custody.

The signing roles must be separated: ROOT may approve signer/key policy, SOURCE may attest independently reviewed commit/tree, BUILDER may attest the build recipe/materials/workflow and artifact, and RELEASE may authorize exact platform and release targets. Roles must not share private key identity. Real-world source and build attestations must derive from controlled CI/reproducible builds and independent evidence (SLSA-style provenance or stronger) rather than self-reported source_commit strings alone. A compromised authorized signer can still lie until revoked by a trusted root transition.

Initial root fingerprint MUST be independently authenticated from an out-of-band source. If the attacker controls both proposed public keys and the fingerprint passed into pin_bootstrap_roots, this CI-only model necessarily accepts the attacker (positive negative-control test). A public-key fingerprint copied from an untrusted download is never a trust root.

Root policy and release provenance include signed timestamps, version and sequence comparisons, but require a protected trusted time and monotonic floor from the caller. They do not implement persistent state or trusted time themselves. The tests intentionally show repeated signed releases can be accepted with an unchanged caller floor.

## Remaining separate P1 blockers — DO NOT conflate

**P1-BROKER/SAME-UID — HOLD:** No separately trusted installer executable, root/keyring storage, broker, privileged activation pointer, destination ownership, immutable journal or authenticated FD transfer. Older after-last-namespace-check and after-last-byte-check same-UID races in the synthetic transaction lab are NOT fixed by root signatures. An OS-enforced broker must own all destination/activation/policy resources outside the hostile UID's writable domain. A Python class, global flock on slash, or another path check is NOT a security boundary. Real installer/unpacker is not present.

**P1-ROLLBACK/FRESHNESS — HOLD:** No broker-owned durable monotonic root version/release sequence, trusted freshness clock, key revocation delivery service, disk crash-consistent atomic journal, power-failure recovery, or replay protections if the caller supplies a stale floor. Those require separate architecture and independent attack tests.

**P1-PRODUCTION KEY/PROVENANCE — HOLD:** No production root/key signers, authenticated out-of-band bootstrap, real builder identities/attestations, real signed release artifact, independent source review ceremony or compromised-signer incident response. Executable CI-only acceptance is NOT production trust authorization.

**Cross-platform HOLD:** Linux Python synthetic tests neither establish native Windows/macOS equivalent protected-handle semantics nor physical Raspberry Pi/Pop!_OS installation, v0.3.1 historical archive preservation, installed v0.3.2.dev4 safety, pipx, sudoers, QSettings/XDG, readsb/tar1090 and SDR hardware. Real package extraction, rollback/uninstall, SBOM/licenses/NOTICE and signed release gates are not tested.

## Security acceptance and independent review

- Root bootstrap/2-of-3 and dual-quorum rotation, revoked signer/reused ID, old/new root policy and role authority: CI-only scoped PASS only after exact-HEAD tests.
- Signed source, build and release chain and actual artifact digest: CI-only scoped PASS only after exact-HEAD tests. The design attests signer-issued CLAIMS, not ground-truth external CI execution.
- Durable rollback, owner-independent OS broker/activation, legitimate authenticated production keys, native platform parity and real installer: all P1 HOLD.
- Existing Agent 06 should independently audit exact commit and attack pin-origin/role/quorum bypass, revision/revocation, source evidence, forged builder attestations, downgrade/replay and signed artifact cross-linking. Publish P0/P1/P2 PASS/HOLD and preserve older independent QA.

No merge, install, uninstall, public release, host hardware access, SDR/service changes or real signing-key operations are permitted by this Draft. **PUBLIC RELEASE HOLD.**
