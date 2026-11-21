# TIHULU FLIGHT RADAR — OLD VERSIONS (immutable preservation)

Purpose: keep the exact versions that ran on the owner's machine / the live site on
2026-11-20/21 recoverable after any future update. NEVER edit files in this tree;
add a NEW dated snapshot instead.

## Contents
- `web-pages-0.3.2.dev4-20261121/` — byte-exact GitHub Pages deployment (46 MB, includes
  bundled upstream tar1090). Restore: copy the tree to any static host. PROVENANCE.txt
  has origin URLs and SHA-256 verification. NOTE: this bundle predates the
  renderCoverageStatus() fix (PR #58) — it is preserved AS DEPLOYED, bug included.
- `desktop-0.3.2.dev4-20261121.md` — the installed desktop build's identity, provenance
  (source commit 950f8278), integrity evidence (41/41 vs private backup) and reinstall recipe.

## Rules
1. Append-only: new versions get a new dated folder; existing snapshots are immutable.
2. Provenance in every snapshot: origin URL/branch, source commit, build source revision,
   date, verifier, and hash checks where applicable.
3. Companion immutable pointer branch (created with this snapshot):
   `old-versions/desktop-0.3.2.dev4-20261121` @ 950f8278a625ce13a9a3c7e21bf9bf76d4b5888e —
   protects the source even if the original topic branch is deleted.
4. The private owner-only backup (~/.local/opt/..., 700/600) remains the system-level
   restore path; this folder is the in-repo record of WHAT ran.

## Verified state at snapshot time
- Desktop: 0.3.2.dev4 running, Internet sources working, RF reception unverified (honest).
- Web: live on both Pages origins, byte-identical assets, source-revision main 059b391.
