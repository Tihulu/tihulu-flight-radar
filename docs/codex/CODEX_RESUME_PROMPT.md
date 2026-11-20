# Codex resume prompt — TIHULU Flight Radar (stable-first)

> Paste the section below into a NEW Codex session with access to this repository. It requests safe read-only verification and a continuation plan, **not an upgrade or deployment**. **Public release: HOLD.**

## Copy-paste prompt

Continue **TIHULU Flight Radar stable-first**, preserving the user-verified **0.3.1** version and keeping **0.3.2.dev4** optional. Do not replace the user's native pipx installation or claim that newer development/security Drafts are approved stable releases.

**Repository:** `Tihulu/tihulu-flight-radar`  
**Documentation handoff branch:** `docs/stable-first-codex-handoff-20261120` (Draft PR #57; not merged)  
**Protected stable branch:** `legacy/v0.3.1` at `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6`  
**Prior security checkpoint:** Draft PR #55; check newer PRs and live HEAD/CI before making any claims.

### Step 1 — Read and verify
1. Read root `AGENTS.md` **first**; it contains the canonical Flight Radar constraints and dual Pages contract.
2. Read `docs/codex/START_HERE.md`, `STATE.json`, `KNOWLEDGE.jsonl`, `HISTORY.md`, `SEARCH_INDEX.md` and this file from the documentation handoff branch, plus `README.md`, `docs/POP_OS_VERSION_SWITCH_AND_LEGACY.md` and `docs/DUAL_GITHUB_PAGES.md`.
3. Verify the `legacy/v0.3.1` SHA. Inspect [prior security Draft PR #55](https://github.com/Tihulu/tihulu-flight-radar/pull/55), its exact SHA and CI, and any later independent QA; do not confuse disposable broker tests with installed security acceptance.

### Step 2 — Reconstruct the stable-first plan
- Maintain native Linux receiver via `readsb` and borrowed `tar1090`. Qt WebEngine is display-only: native reception must not depend on browser WebUSB. Internet-only aircraft must work without claiming the SDR.
- Preserve honest aircraft provenance **I** (Internet), **R** (local RF), **I/R** (same ICAO in both). Never synthesize planes or RF counts. Preserve stale-data expiry, provider attribution and rate-limit limits, radar details and original full tar1090 UI.
- Preserve owner-installed 0.3.1 and its pinned rollback path. A 0.3.2.dev4 preview is opt-in; `main` is not a substitute rollback target.
- Preserve independent external receiver services: no stopping/restarting `readsb` or `tar1090` on app Quit, test cleanup or uninstall; no unauthorized SDR access, sudoers/polkit edits or privileged broker activation.
- Distinguish static tests from live provider and real RTL-SDR tests. Plan isolated Linux QA plus separately gated Windows, macOS and Raspberry Pi parity.
- If proposing Pages updates, verify **both** standalone and TEXT CENTER mirror use the same source SHA and functioning assets; do not publish or hand-edit either site without approval.

### Step 3 — Knowledge and local retrieval
- Use only documented source-linked chunks for offline FTS5 and optional strictly local embeddings. `KNOWLEDGE.jsonl` is not a generated vector database; do not claim otherwise.
- Append historical decisions; update STATE and knowledge with actual reviewed SHAs and source links. Keep immutable legacy and old Draft PRs untouched.
- Propose work via new isolated Draft PRs; **no merge, install, firmware/driver changes, service changes, web deployment, real RF tests or public release without separate owner approval.**

## Required output (in Turkish to the user)

Produce a compact evidence-based status report with:
- Exact source branch/commit and links actually inspected; distinguish baseline, current Draft, and installed runtime.
- Scoped PASS/HOLD for source integrity, isolated build, clean install, rollback/uninstall, native device/UI parity, security, licensing, and public release.
- Blockers grouped P0/P1/P2 and concrete next owner-safe tasks.
- Whether the local FTS index was executed/tested and whether semantic embeddings were actually generated; do not claim vectorization otherwise.
- A copyable next-session handoff, plus proposed documentation-only updates to STATE.json, KNOWLEDGE.jsonl and append-only HISTORY.md.

Never invent percentages, test results, successful hardware reception, model availability or release approval. Keep technical GitHub documentation in English.
