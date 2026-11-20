# FLIGHT — Codex Stable-First Handoff

Updated: 2026-11-20 (UTC). Status: **PUBLIC RELEASE HOLD**. This branch is documentation-only and is not an approved stable release.

## Read order (minimum context)
1. This file (constraints + entry point).
2. [STATE.json](STATE.json) (machine-readable exact baseline, current Draft, blockers, next actions).
3. [KNOWLEDGE.jsonl](KNOWLEDGE.jsonl) (small source-linked retrieval chunks; not embeddings).
4. [HISTORY.md](HISTORY.md) (append-only historical decisions).
5. Project source and evidence referenced in STATE; on Flight Radar also read existing root `AGENTS.md`.

## Current scope
Keep the known-good Flight Radar 0.3.1 stable source and optional 0.3.2.dev4 preview separate; security and public release HOLD.

**Baseline:** `legacy/v0.3.1` / `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6` — user-verified working legacy source baseline.

**Latest inspected work:** [Draft PR #55](https://github.com/Tihulu/tihulu-flight-radar/pull/55) at `2e7ef7246787fcb210fa19ab6436d1da0ce0ff28` — CI-only root-broker security changes; not owner-host deployed. Exact CI/head must be freshly rechecked before working.

## Non-negotiable invariants
- Do not change legacy/v0.3.1, the owner's pipx installation, readsb/tar1090, SDR ownership or settings.
- No merge, release, service restart, sudoers/polkit modifications or real hardware operations.
- Native desktop uses readsb rather than WebUSB; browser SDR path is separate and optional.
- Internet-only must work without antenna; I, R and I/R indicate real provenance, never mock aircraft.

## Safe continuation
1. Read existing root AGENTS.md, README.md, docs/POP_OS_VERSION_SWITCH_AND_LEGACY.md and this handoff.
2. Verify legacy branch checksum and latest PR #55/CI before claiming scoped passes.
3. Plan isolated regression suite for I/R deduplication, tar1090, receiver safety and dual Pages parity.
4. Maintain opt-in 0.3.2.dev4 preview; do not silently replace the user-verified 0.3.1 baseline.

## Retrieval indexing
Run `python3 docs/codex/index_local.py index` for an offline FTS5 search index stored outside Git; then `python3 docs/codex/index_local.py search "query"`. For **genuine semantic vectors**, run the same commands with `--model-dir /path/to/already-installed-local-embedding-model` using locally installed `sentence-transformers`. This is opt-in, strictly offline, no model download or cloud transmission; `KNOWLEDGE.jsonl` is vector-ready, not yet vector-embedded. Never commit private raw data or machine-generated index databases.

## Handoff updates
On a meaningful milestone, append HISTORY, update STATE + knowledge chunks, link exact PR head/CI URLs and PASS/HOLD claims. Do not overwrite history or infer acceptance from a CI green badge. Create a NEW isolated Draft PR; do not merge, tag, release or install without the owner's explicit separate approval.
