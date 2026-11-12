# TIHULU FLIGHT RADAR — TWO PAGES CONTRACT (read before every change)

**Source of truth:** `Tihulu/tihulu-flight-radar` — never develop a second, divergent Flight Radar app in TEXT CENTER.

The **same browser build** must be published at BOTH addresses:
1. Standalone: https://tihulu.github.io/tihulu-flight-radar/
2. TEXT CENTER: https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/

Canonical browser source: `tihulu_flight_radar/web/` in `Tihulu/tihulu-flight-radar`. Preserve its direct WebUSB 1090 MHz reception, genuine RF/Internet/Both provenance, altitude colors, tar1090 backend-health gating, PWA, filters, Hard Stop/USB release, and existing native Windows/Linux/macOS/Pi clients. Never silently auto-claim SDR from a different app. No simulated aircraft data.

**Active reviewed source ref (Nov 6, 2026):** `feature/github-pages-local-bridge-2026-11-06` (draft PR #6). Until approved merge, do not assume `main` has the current browser implementation. Once PR #6 is merged, *atomically update both publishing workflows and this document to `main`*. Do not delete the feature ref before verifying both live sites.

## Mandatory dual publication on every browser update

- Edit and test source in the Flight Radar repository. Do not hand-edit the mirrored `TIHULU-TEXT-CENTER/flight_radar/` as a second source.
- The source branch's `.github/workflows/pages.yml` builds and publishes the standalone site on `gh-pages`. The default-branch `.github/workflows/standalone-pages.yml` supplies scheduled/manual recovery using the same source ref; neither requires deploying through an unconfigured `github-pages` environment.
- The TEXT CENTER repository's `.github/workflows/sync-flight-radar-pages.yml` fetches that *same* source branch and publishes the built files under `flight_radar/` on its existing `gh-pages` branch. It also polls periodically and accepts `workflow_dispatch`. Do not disrupt the Satellite, RF Geolocation, Radio or other TEXT CENTER pages.
- **Publication gates:** both Actions jobs green; both URLs return index.html; bundled `vendor/rtlsdr.mjs` and adsb worker present; both `source-revision.json` files contain the exact same `source_sha` and ideally have byte-identical browser assets. This file is generated during each publish.
- Bump PWA service worker cache version when changing browser assets. Test the two origins separately because WebUSB permissions and cached PWAs are per-origin.
- For urgent user-requested changes, trigger/commit the TEXT CENTER sync on that same turn; scheduled polling is the fallback, not a claim of instant synchronization.
- Do not claim Pages is live merely because a source-branch CI check passed. **Standalone Pages uses GitHub Settings → Pages → Deploy from a branch → `gh-pages` / `(root)`**; its GitHub Actions push alone is insufficient unless the Pages source is configured. If not enabled, report the precise remaining setup action.
- When reporting completed work, always give **both URLs**, active source commit, mirror sync commit, test results and explicit blockers; avoid calling the Flight Radar project complete when only one website was updated.

Full upstream tar1090 frontend is bundled from pinned GPL-2.0-or-later source via `scripts/build-web-tar1090.sh`, including the same-origin `tar1090-adapter.js` and real source data. Never substitute a simplified tar-lookalike for user-requested full aircraft/photo/details controls. Keep source attribution, RF/Internet provenance, and no simulated observations. A public CORS relay is experimental and may not reliably provide Internet aircraft. Never claim third-party backend or photo API has been validated without live tests.

Mirror details: `docs/DUAL_GITHUB_PAGES.md` in this repository and `docs/FLIGHT_RADAR_DUAL_PAGES.md` in TEXT CENTER.

This file is a durable handoff instruction for every coding agent and future development conversation. It supplements rather than overrides existing project preservation/release requirements.
